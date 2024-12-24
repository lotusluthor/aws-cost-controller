# AWS Cost Management Script Guide

This guide explains how to use the AWS cost management script and verify its actions using AWS CLI commands. The script helps you control AWS costs by setting up budget alerts, monitoring resources, and automating resource shutdown.

## Prerequisites

Before using this script, you need:

1. Python 3.8 or later installed
2. AWS CLI installed and configured
3. AWS credentials with appropriate permissions
4. The boto3 library installed

## Setup Instructions

First, install the required dependencies:

```bash
pip install boto3
```

Configure your AWS credentials if you haven't already:

```bash
aws configure
```

When prompted, enter your:
- AWS Access Key ID
- AWS Secret Access Key
- Default region (e.g., us-east-1)
- Default output format (json recommended)

## Running the Script

1. Save the script as `aws_cost_manager.py`

2. Edit the main function to set your budget and email:

```python
manager = AWSCostManager(
    monthly_budget=100.0,  # Your monthly budget in USD
    email='your.email@example.com'  # Your email for notifications
)
```

3. Run the script:

```bash
python aws_cost_manager.py
```

## Verifying Script Actions

After running the script, use these AWS CLI commands to verify each component was set up correctly:

### 1. Budget Alerts

Check if the budget was created:

```bash
aws budgets describe-budgets \
    --account-id $(aws sts get-caller-identity --query 'Account' --output text)
```

View budget notifications:

```bash
aws budgets describe-notifications-for-budget \
    --account-id $(aws sts get-caller-identity --query 'Account' --output text) \
    --budget-name "monthly-budget-$(date +%Y-%m-%d)"
```

### 2. Resource Monitoring

List CloudWatch alarms for CPU utilization:

```bash
aws cloudwatch describe-alarms \
    --query 'MetricAlarms[?starts_with(AlarmName, `LowCPU-`)]'
```

Check specific alarm details:

```bash
aws cloudwatch describe-alarms \
    --alarm-names "LowCPU-i-XXXXX" # Replace with your instance ID
```

### 3. Resource Management

List running EC2 instances:

```bash
aws ec2 describe-instances \
    --filters "Name=instance-state-name,Values=running" \
    --query 'Reservations[].Instances[].[InstanceId,Tags[?Key==`Environment`].Value]' \
    --output table
```

Check instances scheduled for shutdown:

```bash
aws ec2 describe-instances \
    --filters "Name=tag:Environment,Values=Development,Testing,Dev,Test" \
    "Name=instance-state-name,Values=running" \
    --query 'Reservations[].Instances[].[InstanceId,State.Name]' \
    --output table
```

### 4. Cost Analysis

Get current month's cost:

```bash
aws ce get-cost-and-usage \
    --time-period Start=$(date +%Y-%m)-01,End=$(date +%Y-%m-%d) \
    --granularity MONTHLY \
    --metrics "UnblendedCost" \
    --query 'ResultsByTime[].Total.UnblendedCost.Amount'
```

View service-specific costs:

```bash
aws ce get-cost-and-usage \
    --time-period Start=$(date +%Y-%m)-01,End=$(date +%Y-%m-%d) \
    --granularity MONTHLY \
    --metrics "UnblendedCost" \
    --group-by Type=DIMENSION,Key=SERVICE \
    --query 'ResultsByTime[].Groups[].[Keys[0],Metrics.UnblendedCost.Amount]' \
    --output table
```

## Troubleshooting

If you encounter issues, check the following:

1. Verify AWS credentials are correctly configured:
```bash
aws sts get-caller-identity
```

2. Confirm required IAM permissions:
```bash
aws iam get-user
aws iam list-attached-user-policies
```

3. Check CloudWatch Logs for any error messages:
```bash
aws logs describe-log-groups
```

## Common Issues and Solutions

1. "AccessDenied" errors:
   - Verify your IAM user has the necessary permissions
   - Required permissions include: budgets:*, cloudwatch:*, ec2:*, ce:*

2. Budget already exists:
   - Use the describe-budgets command above to check existing budgets
   - Delete existing budget if needed:
     ```bash
     aws budgets delete-budget \
         --account-id $(aws sts get-caller-identity --query 'Account' --output text) \
         --budget-name "monthly-budget-$(date +%Y-%m-%d)"
     ```

3. CloudWatch alarms not appearing:
   - Wait a few minutes for alarms to propagate
   - Verify instance IDs are correct
   - Check if CloudWatch has necessary permissions

## Best Practices

1. Regularly check your cost dashboard using:
```bash
aws ce get-cost-and-usage-with-resources \
    --time-period Start=$(date -d "$(date +%Y-%m-01)" +%Y-%m-%d),End=$(date +%Y-%m-%d) \
    --granularity MONTHLY \
    --metric "UnblendedCost"
```

2. Monitor resource states daily:
```bash
aws ec2 describe-instances \
    --query 'Reservations[].Instances[].[InstanceId,State.Name,Tags[?Key==`Environment`].Value]' \
    --output table
```

3. Review CloudWatch alarms regularly:
```bash
aws cloudwatch describe-alarms \
    --state-value ALARM \
    --output table
```

Remember to clean up resources when no longer needed to avoid ongoing charges. Use these commands carefully in production environments, as they can affect running resources.
