# AWS EC2 Instance Provisioning Script

A Python script that provisions multiple AWS EC2 instances in parallel using boto3 and concurrent.futures. This script provides efficient, scalable provisioning with comprehensive error handling and logging.

## Features

- **Parallel Provisioning**: Provision multiple EC2 instances simultaneously using ThreadPoolExecutor
- **Comprehensive Configuration**: Support for all major EC2 instance parameters
- **Error Handling**: Robust error handling with detailed logging
- **Flexible Configuration**: JSON-based configuration files for easy instance management
- **Cleanup Capabilities**: Built-in instance termination and cleanup
- **Detailed Logging**: Both file and console logging with configurable levels
- **AWS Best Practices**: Follows AWS security and tagging best practices

## Prerequisites

- Python 3.7+
- AWS CLI configured with appropriate credentials
- Required IAM permissions for EC2 operations

### Required IAM Permissions

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "ec2:RunInstances",
                "ec2:DescribeInstances",
                "ec2:DescribeRegions",
                "ec2:CreateTags",
                "ec2:TerminateInstances",
                "ec2:DescribeVolumes",
                "ec2:DescribeSecurityGroups",
                "ec2:DescribeSubnets"
            ],
            "Resource": "*"
        }
    ]
}
```

## Installation

1. Clone or download the script files
2. Install required dependencies:

```bash
pip install -r requirements.txt
```

## Configuration

### Creating a Configuration File

The script uses JSON configuration files to define EC2 instances. Configuration files are stored in the `configs/` directory. You can create a sample configuration file:

```bash
python aws_ec2_provisioning.py --sample
```

This will create `configs/sample_config.json` with example configurations.

### Configuration Format

```json
[
    {
        "name": "web-server-1",
        "instance_type": "t3.micro",
        "image_id": "ami-0c55b159cbfafe1f0",
        "key_name": "my-key-pair",
        "security_group_ids": ["sg-12345678"],
        "subnet_id": "subnet-12345678",
        "user_data": "#!/bin/bash\necho 'Hello from User Data'",
        "tags": {
            "Environment": "Production",
            "Project": "WebApp"
        },
        "volume_size": 20,
        "volume_type": "gp3",
        "iam_instance_profile": "my-instance-profile"
    }
]
```

### Configuration Parameters

| Parameter | Required | Description | Default |
|-----------|----------|-------------|---------|
| `name` | Yes | Instance name (used for tagging) | - |
| `instance_type` | Yes | EC2 instance type (e.g., t3.micro) | - |
| `image_id` | Yes | AMI ID | - |
| `key_name` | Yes | SSH key pair name | - |
| `security_group_ids` | Yes | List of security group IDs | - |
| `subnet_id` | Yes | Subnet ID for instance placement | - |
| `user_data` | No | User data script for instance initialization | None |
| `tags` | No | Additional tags for the instance | {} |
| `volume_size` | No | EBS volume size in GB | 8 |
| `volume_type` | No | EBS volume type | gp3 |
| `iam_instance_profile` | No | IAM instance profile name | None |
| `spot_instance` | No | Use spot instances instead of on-demand | False |
| `spot_max_price` | No | Maximum price for spot instances (optional) | None |
| `spot_max_retries` | No | Maximum retry attempts for spot instances | 3 |
| `spot_retry_delay` | No | Initial delay between retries in seconds | 30 |

## Usage

### Basic Usage

```bash
python aws_ec2_provisioning.py --config instances.json
```

### Advanced Usage

```bash
# Specify region and number of parallel workers
python aws_ec2_provisioning.py \
    --config instances.json \
    --region us-west-2 \
    --workers 10

# Provision instances and then clean them up
python aws_ec2_provisioning.py \
    --config instances.json \
    --cleanup
```

### Command Line Options

| Option | Short | Description | Default |
|--------|-------|-------------|---------|
| `--config` | `-c` | Path to configuration JSON file | Required |
| `--region` | `-r` | AWS region name | us-east-1 |
| `--workers` | `-w` | Maximum parallel workers | 5 |
| `--cleanup` | - | Clean up instances after provisioning | False |
| `--sample` | - | Create sample configuration file | False |

## Examples

### Example 1: Basic Provisioning

```bash
# Create sample config
python aws_ec2_provisioning.py --sample

# Edit the config file with your values
nano sample_config.json

# Provision instances
python aws_ec2_provisioning.py --config sample_config.json
```

### Example 2: High-Throughput Provisioning

```bash
# Provision 50 instances with 20 parallel workers
python aws_ec2_provisioning.py \
    --config large_deployment.json \
    --workers 20 \
    --region us-east-1
```

### Example 3: Development Environment

```bash
# Provision instances and automatically clean up
python aws_ec2_provisioning.py \
    --config dev_instances.json \
    --cleanup
```

## Output

The script provides:

1. **Console Output**: Real-time status updates during provisioning
2. **Log File**: Detailed logs saved to `ec2_provisioning.log`
3. **Results File**: JSON file with provisioning results saved to `provisioning_results.json`

### Sample Output

```
============================================================
PROVISIONING RESULTS
============================================================
✅ web-server-1: i-1234567890abcdef0 (54.123.45.67)
✅ app-server-1: i-0987654321fedcba0 (54.123.45.68)

Results saved to 'provisioning_results.json'
```

## Error Handling

The script includes comprehensive error handling:

- **Credential Validation**: Checks AWS credentials before starting
- **Instance-Level Errors**: Continues provisioning other instances if one fails
- **Detailed Error Messages**: Provides specific error information for troubleshooting
- **Graceful Degradation**: Handles partial failures gracefully

## Logging

Logs are written to both:
- **Console**: Real-time feedback during execution
- **File**: `ec2_provisioning.log` for detailed analysis

Log levels include INFO, WARNING, and ERROR with timestamps.

## Security Features

- **Encrypted EBS Volumes**: All volumes are encrypted by default
- **Proper Tagging**: Instances are tagged with creation metadata
- **IAM Integration**: Support for IAM instance profiles
- **Security Group Validation**: Uses specified security groups

## Spot Instance Support

The script supports both on-demand and spot instances for cost optimization:

### **Spot Instance Benefits:**
- **Cost Savings**: Up to 90% off on-demand pricing
- **Flexible Pricing**: Set your own maximum price or let AWS use current on-demand price
- **Parallel Processing**: Perfect for development, testing, and batch workloads

### **Spot Instance Configuration:**
```json
{
  "name": "cost-effective-test",
  "instance_type": "t3.micro",
  "image_id": "ami-12345678",
  "spot_instance": true,
  "spot_max_price": "0.01"  // Optional: 1 cent per hour max
}
```

### **When to Use Spot Instances:**
- **Development/Testing**: Non-critical workloads that can handle interruptions
- **Batch Processing**: Jobs that can restart if interrupted
- **CI/CD Pipelines**: Temporary build environments
- **Data Analysis**: When cost is more important than availability

### **Spot Instance Considerations:**
- **Interruption Risk**: Instances can be terminated with 2-minute warning
- **Price Fluctuations**: Set realistic max prices based on your budget
- **Availability**: Varies by region, instance type, and time of day
- **Best for Stateless**: Applications that can handle restarts gracefully

### **Retry Mechanism:**
The script includes intelligent retry logic for spot instances:

- **Automatic Retries**: Up to 3 attempts by default (configurable)
- **Exponential Backoff**: Delay increases between retries (30s → 60s → 120s)
- **Smart Cleanup**: Failed spot requests are automatically cancelled
- **Configurable**: Set custom retry counts and delays per instance

```json
{
  "name": "resilient-spot",
  "spot_instance": true,
  "spot_max_retries": 5,      // Try up to 5 times
  "spot_retry_delay": 60      // Start with 60 second delays
}
```

## Performance Considerations

- **Parallel Processing**: Configurable number of parallel workers
- **Efficient API Usage**: Minimizes AWS API calls
- **Resource Management**: Proper cleanup and resource tracking

## Troubleshooting

### Common Issues

1. **AWS Credentials**: Ensure AWS CLI is configured or environment variables are set
2. **Permissions**: Verify IAM permissions for EC2 operations
3. **Region Availability**: Check that AMIs and instance types are available in your region
4. **Resource Limits**: Ensure you haven't hit AWS service limits

### Debug Mode

For detailed debugging, you can modify the logging level in the script:

```python
logging.basicConfig(level=logging.DEBUG)
```

## Contributing

Feel free to submit issues, feature requests, or pull requests to improve the script.

## License

This script is provided as-is for educational and operational purposes.

## Support

For issues or questions:
1. Check the logs in `ec2_provisioning.log`
2. Verify AWS credentials and permissions
3. Review the configuration file format
4. Check AWS service status and limits
