# AWS Cost Manager

A Python script for managing AWS costs, monitoring resources, and implementing cost-saving measures across EC2, ECS, ECR, and EKS services.

## Prerequisites

- Python 3.6 or higher
- Boto3 library (`pip install boto3`)
- AWS CLI configured with appropriate credentials
- Required AWS IAM permissions for:
  - AWS Budgets
  - EC2
  - CloudWatch
  - ECS
  - ECR
  - EKS
  - Cost Explorer

## Configuration

1. Edit the main() function in the script to set your budget and email:
```python
manager = AWSCostManager(
    monthly_budget=75.00,  # Set your desired monthly budget in USD
    email='your.email@example.com'  # Set your notification email
)
```

2. Ensure your AWS credentials are configured:
```bash
aws configure
```

## Running the Script

```bash
python aws_cost_manager.py
```

## Verifying Resources

### Budget Alerts
Check if budget alerts were created:
```bash
aws budgets describe-budgets --account-id $(aws sts get-caller-identity --query Account --output text)
```

### CloudWatch Alarms
List all CloudWatch alarms:
```bash
aws cloudwatch describe-alarms --alarm-name-prefix "LowCPU-"
```

View ECS service alarms:
```bash
aws cloudwatch describe-alarms --alarm-name-prefix "ECS-LowCPU-"
```

View ECR storage alarms:
```bash
aws cloudwatch describe-alarms --alarm-name-prefix "ECR-HighStorage-"
```

View EKS cluster alarms:
```bash
aws cloudwatch describe-alarms --alarm-name-prefix "EKS-"
```

### EC2 Instances
List running development/testing instances:
```bash
aws ec2 describe-instances \
    --filters "Name=tag:Environment,Values=Development,Testing,Dev,Test" \
    "Name=instance-state-name,Values=running" \
    --query 'Reservations[].Instances[].{ID:InstanceId,Env:Tags[?Key==`Environment`].Value|[0]}' \
    --output table
```

### Container Services

List ECS clusters:
```bash
aws ecs list-clusters
```

List ECR repositories and lifecycle policies:
```bash
aws ecr describe-repositories
aws ecr get-lifecycle-policy --repository-name REPO_NAME
```

List EKS clusters:
```bash
aws eks list-clusters
```

### Cost Reports
Get current month's costs:
```bash
aws ce get-cost-and-usage \
    --time-period Start=$(date -d "$(date +%Y-%m-01)" +%Y-%m-%d),End=$(date +%Y-%m-%d) \
    --granularity MONTHLY \
    --metrics UnblendedCost \
    --group-by Type=DIMENSION,Key=SERVICE
```

## Troubleshooting

1. Check CloudWatch Logs for any errors:
```bash
aws logs describe-log-streams --log-group-name /aws/lambda/cost-manager
```

2. Verify IAM permissions:
```bash
aws iam get-user
aws iam list-attached-user-policies --user-name YOUR_USERNAME
```

3. Test AWS CLI access:
```bash
aws sts get-caller-identity
```

## Common Issues

1. **Budget Creation Fails**
   - Verify account ID is correct
   - Ensure you have budgets:WriteBudget permission

2. **Alarm Creation Fails**
   - Check if you've reached the CloudWatch alarms limit
   - Verify CloudWatch permissions

3. **Resource Shutdown Fails**
   - Check EC2 permissions
   - Verify instance tag names match the script

## Security Best Practices

1. Use IAM roles with minimum required permissions
2. Regularly rotate AWS access keys
3. Enable AWS CloudTrail for audit logging
4. Use VPC endpoints for AWS services where possible
5. Implement proper tagging strategy for resources

## Cost Optimization Tips

1. Tag all resources properly for cost allocation
2. Review CloudWatch alarms regularly
3. Adjust budget thresholds based on usage patterns
4. Monitor ECR image cleanup policies
5. Review EKS node group sizing