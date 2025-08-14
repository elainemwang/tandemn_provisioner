#!/usr/bin/env python3
"""
AWS EC2 Instance Provisioning Script

This script provisions multiple AWS EC2 instances in parallel using boto3 and concurrent.futures.
It supports custom configurations, error handling, and detailed logging.
"""

import boto3
import json
import logging
import time
import os
import base64
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
import argparse
import sys


@dataclass
class EC2InstanceConfig:
    """Configuration for an EC2 instance."""
    instance_type: str
    name: Optional[str] = None
    image_id: Optional[str] = None
    key_name: Optional[str] = None
    security_group_ids: Optional[List[str]] = None
    subnet_id: Optional[str] = None
    user_data: Optional[str] = None
    tags: Optional[Dict[str, str]] = None
    volume_size: int = 8
    volume_type: str = 'gp3'
    iam_instance_profile: Optional[str] = None
    spot_instance: bool = True  # Default to spot instances
    spot_max_price: Optional[str] = None
    spot_max_retries: int = 3
    spot_retry_delay: int = 30


class EC2Provisioner:
    """Handles EC2 instance provisioning in parallel."""
    
    def __init__(self, region_name: str = 'us-east-1', max_workers: int = 5):
        """
        Initialize the EC2 provisioner.
        
        Args:
            region_name: AWS region name
            max_workers: Maximum number of parallel workers
        """
        self.region_name = region_name
        self.max_workers = max_workers
        self.ec2_client = boto3.client('ec2', region_name=region_name)
        self.ec2_resource = boto3.resource('ec2', region_name=region_name)
        
        # Setup logging
        self._setup_logging()
        
        # Validate AWS credentials
        self._validate_credentials()
    
    def _setup_logging(self):
        """Setup logging configuration."""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('ec2_provisioning.log'),
                logging.StreamHandler(sys.stdout)
            ]
        )
        self.logger = logging.getLogger(__name__)
    
    def _validate_credentials(self):
        """Validate AWS credentials and permissions."""
        try:
            # Test AWS credentials by making a simple API call
            self.ec2_client.describe_regions()
            self.logger.info("AWS credentials validated successfully")
        except Exception as e:
            self.logger.error(f"Failed to validate AWS credentials: {e}")
            raise
    
    def _create_block_device_mappings(self, config: EC2InstanceConfig) -> List[Dict[str, Any]]:
        """Create block device mappings for the instance."""
        return [
            {
                'DeviceName': '/dev/sda1',
                'Ebs': {
                    'VolumeSize': config.volume_size,
                    'VolumeType': config.volume_type,
                    'DeleteOnTermination': True,
                    'Encrypted': True
                }
            }
        ]
    
    def _create_tags(self, config: EC2InstanceConfig, instance_id: str) -> List[Dict[str, str]]:
        """Create tags for the instance."""
        tags = [
            {'Key': 'Name', 'Value': config.name},
            {'Key': 'CreatedBy', 'Value': 'EC2Provisioner'},
            {'Key': 'CreationDate', 'Value': time.strftime('%Y-%m-%d')}
        ]
        
        if config.tags:
            for key, value in config.tags.items():
                tags.append({'Key': key, 'Value': value})
        
        return tags
    
    def provision_instance(self, config: EC2InstanceConfig) -> Dict[str, Any]:
        """
        Provision a single EC2 instance (on-demand or spot).
        
        Args:
            config: EC2 instance configuration
            
        Returns:
            Dictionary containing instance information and status
        """
        try:
            # Set default values for missing fields
            config = self._set_defaults(config)
            
            self.logger.info(f"Starting provisioning for instance: {config.name}")
            
            # Prepare common launch parameters (without TagSpecifications for spot instances)
            launch_params = {
                'ImageId': config.image_id,
                'InstanceType': config.instance_type,
                'BlockDeviceMappings': self._create_block_device_mappings(config)
            }
            
            # Add optional parameters only if provided
            if config.key_name:
                launch_params['KeyName'] = config.key_name
            
            if config.security_group_ids:
                launch_params['SecurityGroupIds'] = config.security_group_ids
            
            if config.subnet_id:
                launch_params['SubnetId'] = config.subnet_id
            
            if config.user_data:
                # Encode user data as base64 for spot instances
                launch_params['UserData'] = base64.b64encode(config.user_data.encode('utf-8')).decode('utf-8')
            
            if config.iam_instance_profile:
                launch_params['IamInstanceProfile'] = {'Name': config.iam_instance_profile}
            
            if config.spot_instance:
                return self._launch_spot_instance(config, launch_params)
            else:
                return self._launch_on_demand_instance(config, launch_params)
            
        except Exception as e:
            error_msg = f"Failed to provision instance {config.name}: {str(e)}"
            self.logger.error(error_msg)
            return {
                'name': config.name,
                'status': 'failed',
                'error': str(e)
            }
    
    def _launch_on_demand_instance(self, config: EC2InstanceConfig, launch_params: Dict[str, Any]) -> Dict[str, Any]:
        """Launch an on-demand EC2 instance."""
        # Add MinCount, MaxCount, and TagSpecifications for on-demand instances
        on_demand_params = launch_params.copy()
        on_demand_params['MinCount'] = 1
        on_demand_params['MaxCount'] = 1
        on_demand_params['TagSpecifications'] = [
            {
                'ResourceType': 'instance',
                'Tags': self._create_tags(config, '')
            }
        ]
        
        # Launch the instance
        response = self.ec2_client.run_instances(**on_demand_params)
        instance_id = response['Instances'][0]['InstanceId']
        
        # Wait for instance to be running
        self.logger.info(f"Waiting for instance {instance_id} to be running...")
        waiter = self.ec2_client.get_waiter('instance_running')
        waiter.wait(InstanceIds=[instance_id])
        
        # Get instance details and create result
        return self._finalize_instance(config, instance_id, 'on-demand')
    
    def _launch_spot_instance(self, config: EC2InstanceConfig, launch_params: Dict[str, Any]) -> Dict[str, Any]:
        """Launch a spot EC2 instance with retry logic."""
        max_retries = config.spot_max_retries
        retry_delay = config.spot_retry_delay  # seconds
        
        for attempt in range(max_retries):
            try:
                self.logger.info(f"Spot instance attempt {attempt + 1}/{max_retries} for {config.name}")
                
                # Create spot instance request
                spot_request_params = {
                    'LaunchSpecification': launch_params,
                    'Type': 'one-time'
                }
                
                # Add max price if specified (optional - AWS will use on-demand price if not set)
                if config.spot_max_price:
                    spot_request_params['SpotPrice'] = config.spot_max_price
                    self.logger.info(f"Setting spot max price to: {config.spot_max_price}")
                else:
                    self.logger.info(f"No max price specified - AWS will use current on-demand price")
                
                # Request spot instance
                self.logger.info(f"Requesting spot instance for {config.name}...")
                spot_response = self.ec2_client.request_spot_instances(**spot_request_params)
                spot_request_id = spot_response['SpotInstanceRequests'][0]['SpotInstanceRequestId']
                
                # Wait for spot request to be fulfilled
                self.logger.info(f"Waiting for spot request {spot_request_id} to be fulfilled...")
                waiter = self.ec2_client.get_waiter('spot_instance_request_fulfilled')
                waiter.wait(SpotInstanceRequestIds=[spot_request_id])
                
                # Get the instance ID from the fulfilled request
                spot_request = self.ec2_client.describe_spot_instance_requests(
                    SpotInstanceRequestIds=[spot_request_id]
                )['SpotInstanceRequests'][0]
                
                instance_id = spot_request['InstanceId']
                
                # Wait for instance to be running
                self.logger.info(f"Waiting for spot instance {instance_id} to be running...")
                waiter = self.ec2_client.get_waiter('instance_running')
                waiter.wait(InstanceIds=[instance_id])
                
                # Get instance details and create result
                result = self._finalize_instance(config, instance_id, 'spot')
                result['spot_request_id'] = spot_request_id
                
                # Tag the spot instance (since TagSpecifications isn't supported in launch)
                try:
                    self.ec2_client.create_tags(
                        Resources=[instance_id],
                        Tags=self._create_tags(config, instance_id)
                    )
                    self.logger.info(f"Successfully tagged spot instance {instance_id}")
                except Exception as tag_error:
                    self.logger.warning(f"Failed to tag spot instance {instance_id}: {tag_error}")
                
                self.logger.info(f"Spot instance {config.name} successfully provisioned on attempt {attempt + 1}")
                return result
                
            except Exception as e:
                error_msg = f"Spot instance attempt {attempt + 1} failed for {config.name}: {str(e)}"
                self.logger.warning(error_msg)
                
                # Clean up failed spot request if it exists
                if 'spot_request_id' in locals():
                    try:
                        self.logger.info(f"Cancelling failed spot request {spot_request_id}")
                        self.ec2_client.cancel_spot_instance_requests(
                            SpotInstanceRequestIds=[spot_request_id]
                        )
                    except Exception as cleanup_error:
                        self.logger.warning(f"Failed to cancel spot request: {cleanup_error}")
                
                # If this was the last attempt, raise the error
                if attempt == max_retries - 1:
                    raise Exception(f"All {max_retries} spot instance attempts failed for {config.name}. Last error: {str(e)}")
                
                # Wait before retrying
                self.logger.info(f"Waiting {retry_delay} seconds before retry...")
                time.sleep(retry_delay)
                
                # Increase delay for next attempt (exponential backoff)
                retry_delay = min(retry_delay * 2, 120)  # Cap at 2 minutes
    
    def _finalize_instance(self, config: EC2InstanceConfig, instance_id: str, instance_type: str) -> Dict[str, Any]:
        """Finalize instance setup and return result."""
        # Get instance details
        instance = self.ec2_resource.Instance(instance_id)
        
        # Create and attach EBS volume tags
        for volume in instance.volumes.all():
            self.ec2_client.create_tags(
                Resources=[volume.id],
                Tags=self._create_tags(config, instance_id)
            )
        
        result = {
            'name': config.name,
            'instance_id': instance_id,
            'public_ip': instance.public_ip_address,
            'private_ip': instance.private_ip_address,
            'state': instance.state['Name'],
            'status': 'success',
            'instance_type': instance_type
        }
        
        self.logger.info(f"Successfully provisioned {instance_type} instance {config.name} ({instance_id})")
        return result
    
    def provision_instances_parallel(self, configs: List[EC2InstanceConfig]) -> List[Dict[str, Any]]:
        """
        Provision multiple EC2 instances in parallel.
        
        Args:
            configs: List of EC2 instance configurations
            
        Returns:
            List of provisioning results
        """
        self.logger.info(f"Starting parallel provisioning of {len(configs)} instances")
        
        results = []
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all provisioning tasks
            future_to_config = {
                executor.submit(self.provision_instance, config): config 
                for config in configs
            }
            
            # Process completed tasks
            for future in as_completed(future_to_config):
                config = future_to_config[future]
                try:
                    result = future.result()
                    results.append(result)
                    
                    if result['status'] == 'success':
                        self.logger.info(f"Instance {config.name} completed successfully")
                    else:
                        self.logger.error(f"Instance {config.name} failed: {result.get('error', 'Unknown error')}")
                        
                except Exception as e:
                    error_result = {
                        'name': config.name,
                        'status': 'failed',
                        'error': str(e)
                    }
                    results.append(error_result)
                    self.logger.error(f"Unexpected error provisioning {config.name}: {e}")
        
        # Log summary
        successful = len([r for r in results if r['status'] == 'success'])
        failed = len([r for r in results if r['status'] == 'failed'])
        
        self.logger.info(f"Provisioning completed. Successful: {successful}, Failed: {failed}")
        
        return results
    
    def _set_defaults(self, config: EC2InstanceConfig) -> EC2InstanceConfig:
        """Set default values for missing configuration fields."""
        import copy
        
        # Create a copy to avoid modifying the original
        config = copy.deepcopy(config)
        
        # Set default name if not provided
        if not config.name:
            config.name = f"{config.instance_type}-{int(time.time())}"
        
        # Set default Ubuntu 24.04 LTS AMI if not provided
        if not config.image_id:
            # This is a placeholder - you'll need to update this with a valid AMI for your region
            config.image_id = "ami-0ae8595e2aff47037"  # Ubuntu 24.04 LTS in us-east-1
        
        # Set default tags if not provided
        if not config.tags:
            config.tags = {
                "Environment": "Development",
                "Project": "AutoProvisioned",
                "InstanceType": "Spot" if config.spot_instance else "OnDemand"
            }
        
        return config
    
    def terminate_instance(self, instance_id: str) -> bool:
        """
        Terminate a single EC2 instance.
        
        Args:
            instance_id: ID of the instance to terminate
            
        Returns:
            True if successful, False otherwise
        """
        try:
            self.logger.info(f"Terminating instance: {instance_id}")
            self.ec2_client.terminate_instances(InstanceIds=[instance_id])
            return True
        except Exception as e:
            self.logger.error(f"Failed to terminate instance {instance_id}: {e}")
            return False
    
    def cleanup_instances(self, instance_ids: List[str]) -> Dict[str, bool]:
        """
        Clean up multiple instances.
        
        Args:
            instance_ids: List of instance IDs to terminate
            
        Returns:
            Dictionary mapping instance IDs to termination success status
        """
        self.logger.info(f"Starting cleanup of {len(instance_ids)} instances")
        
        results = {}
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_id = {
                executor.submit(self.terminate_instance, instance_id): instance_id 
                for instance_id in instance_ids
            }
            
            for future in as_completed(future_to_id):
                instance_id = future_to_id[future]
                try:
                    success = future.result()
                    results[instance_id] = success
                except Exception as e:
                    self.logger.error(f"Error during cleanup of {instance_id}: {e}")
                    results[instance_id] = False
        
        return results
    



def load_config_from_file(config_file: str) -> List[EC2InstanceConfig]:
    """Load EC2 instance configurations from a JSON file."""
    try:
        with open(config_file, 'r') as f:
            config_data = json.load(f)
        
        configs = []
        for item in config_data:
            config = EC2InstanceConfig(
                instance_type=item['instance_type'],
                name=item.get('name'),
                image_id=item.get('image_id'),
                key_name=item.get('key_name'),
                security_group_ids=item.get('security_group_ids'),
                subnet_id=item.get('subnet_id'),
                user_data=item.get('user_data'),
                tags=item.get('tags'),
                volume_size=item.get('volume_size', 8),
                volume_type=item.get('volume_type', 'gp3'),
                iam_instance_profile=item.get('iam_instance_profile'),
                spot_instance=item.get('spot_instance', True),  # Default to spot
                spot_max_price=item.get('spot_max_price'),
                spot_max_retries=item.get('spot_max_retries', 3),
                spot_retry_delay=item.get('spot_retry_delay', 30)
            )
            configs.append(config)
        
        return configs
    except Exception as e:
        raise Exception(f"Failed to load configuration from {config_file}: {e}")


def create_sample_config():
    """Create a sample configuration file."""
    sample_config = [
        {
            "instance_type": "t3.micro"
        },
        {
            "instance_type": "t3.small",
            "name": "custom-name"
        },
        {
            "instance_type": "t3.medium",
            "spot_instance": False  # Override to on-demand
        }
    ]
    
    with open('sample_config.json', 'w') as f:
        json.dump(sample_config, f, indent=2)
    
    print("Sample configuration file 'sample_config.json' created")


def main():
    """Main function to handle command line arguments and execute provisioning."""
    parser = argparse.ArgumentParser(description='AWS EC2 Instance Provisioning Script')
    parser.add_argument('--config', '-c', help='Path to configuration JSON file')
    parser.add_argument('--region', '-r', default='us-east-1', help='AWS region (default: us-east-1)')
    parser.add_argument('--workers', '-w', type=int, default=5, help='Maximum parallel workers (default: 5)')
    parser.add_argument('--cleanup', action='store_true', help='Clean up instances from previous run (no provisioning)')
    parser.add_argument('--sample', action='store_true', help='Create sample configuration file')
    
    args = parser.parse_args()
    
    if args.sample:
        create_sample_config()
        return
    
    # Handle cleanup mode
    if args.cleanup:
        try:
            # Load previous results and cleanup
            if os.path.exists('provisioning_results.json'):
                with open('provisioning_results.json', 'r') as f:
                    previous_results = json.load(f)
                
                provisioner = EC2Provisioner(region_name=args.region, max_workers=args.workers)
                
                print("Cleaning up instances from previous run...")
                instance_ids = [r['instance_id'] for r in previous_results if r['status'] == 'success']
                
                if instance_ids:
                    cleanup_results = provisioner.cleanup_instances(instance_ids)
                    for instance_id, success in cleanup_results.items():
                        status = "✅" if success else "❌"
                        print(f"{status} {instance_id}")
                else:
                    print("No instances to clean up")
            else:
                print("No previous provisioning results found")
        except Exception as e:
            print(f"Error during cleanup: {e}")
            sys.exit(1)
        return
    

    
    if not args.config:
        parser.error("--config/-c is required unless using --sample or --cleanup")
    
    try:
        # Load configurations
        configs = load_config_from_file(args.config)
        
        # Initialize provisioner
        provisioner = EC2Provisioner(region_name=args.region, max_workers=args.workers)
        
        # Provision instances
        results = provisioner.provision_instances_parallel(configs)
        
        # Print results
        print("\n" + "="*60)
        print("PROVISIONING RESULTS")
        print("="*60)
        
        for result in results:
            if result['status'] == 'success':
                print(f"✅ {result['name']}: {result['instance_id']} ({result['public_ip']})")
            else:
                print(f"❌ {result['name']}: {result.get('error', 'Unknown error')}")
        

        
        # Save results to file
        with open('provisioning_results.json', 'w') as f:
            json.dump(results, f, indent=2)
        
        print(f"\nResults saved to 'provisioning_results.json'")
        
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
