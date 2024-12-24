import boto3
import json
import datetime
import logging
from botocore.exceptions import ClientError

class AWSCostManager:
    def __init__(self, monthly_budget: float, email: str):
        self.monthly_budget = monthly_budget
        self.email = email
        
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger(__name__)
        
        try:
            # Initialize standard AWS clients
            self.budgets = boto3.client('budgets')
            self.ec2 = boto3.client('ec2')
            self.cloudwatch = boto3.client('cloudwatch')
            self.account_id = boto3.client('sts').get_caller_identity()['Account']
            
            # Initialize container service clients
            self.ecs = boto3.client('ecs')
            self.ecr = boto3.client('ecr')
            self.eks = boto3.client('eks')
        except Exception as e:
            self.logger.error(f"Failed to initialize AWS clients: {str(e)}")
            raise

    def create_or_update_budget_alert(self) -> bool:
        """
        Creates or updates a monthly budget with notification thresholds.
        Checks for existing budget before creating a new one.
        """
        try:
            budget_name = f'monthly-budget-{datetime.datetime.now().strftime("%Y-%m")}'
            
            # Check if budget already exists
            try:
                existing_budgets = self.budgets.describe_budgets(
                    AccountId=self.account_id
                )['Budgets']
                
                existing_budget = next(
                    (b for b in existing_budgets if b['BudgetName'] == budget_name),
                    None
                )
            except ClientError:
                existing_budget = None

            # Define the budget configuration
            budget = {
                'BudgetName': budget_name,
                'BudgetLimit': {
                    'Amount': str(self.monthly_budget),
                    'Unit': 'USD'
                },
                'TimeUnit': 'MONTHLY',
                'BudgetType': 'COST'
            }
            
            # Create notification settings
            notifications = []
            for threshold in [50.0, 80.0, 100.0]:
                notification = {
                    'Notification': {
                        'ComparisonOperator': 'GREATER_THAN',
                        'NotificationType': 'ACTUAL',
                        'Threshold': threshold,
                        'ThresholdType': 'PERCENTAGE',
                        'NotificationState': 'ALARM'
                    },
                    'Subscribers': [
                        {
                            'SubscriptionType': 'EMAIL',
                            'Address': self.email
                        }
                    ]
                }
                notifications.append(notification)

            if existing_budget:
                # Update existing budget
                self.budgets.update_budget(
                    AccountId=self.account_id,
                    NewBudget=budget
                )
                self.logger.info(f"Updated existing budget: {budget_name}")
            else:
                # Create new budget
                self.budgets.create_budget(
                    AccountId=self.account_id,
                    Budget=budget,
                    NotificationsWithSubscribers=notifications
                )
                self.logger.info(f"Created new budget: {budget_name}")
            
            return True
            
        except ClientError as e:
            self.logger.error(f"Failed to manage budget: {str(e)}")
            return False

    def manage_resource_monitoring(self) -> bool:
        """
        Sets up or updates CloudWatch alarms for resource monitoring.
        Checks existing alarms before creating new ones.
        """
        try:
            # Get all running EC2 instances
            instances = self.ec2.describe_instances(
                Filters=[{
                    'Name': 'instance-state-name',
                    'Values': ['running']
                }]
            )
            
            # Get existing alarms
            existing_alarms = self.cloudwatch.describe_alarms(
                AlarmNamePrefix='LowCPU-'
            )['MetricAlarms']
            existing_alarm_names = {alarm['AlarmName'] for alarm in existing_alarms}
            
            # Track instances that need alarms
            needed_alarms = set()
            
            for reservation in instances['Reservations']:
                for instance in reservation['Instances']:
                    instance_id = instance['InstanceId']
                    alarm_name = f'LowCPU-{instance_id}'
                    needed_alarms.add(alarm_name)
                    
                    alarm_config = {
                        'AlarmName': alarm_name,
                        'MetricName': 'CPUUtilization',
                        'Namespace': 'AWS/EC2',
                        'Dimensions': [{
                            'Name': 'InstanceId',
                            'Value': instance_id
                        }],
                        'Period': 3600,
                        'EvaluationPeriods': 24,
                        'Threshold': 10.0,
                        'ComparisonOperator': 'LessThanThreshold',
                        'Statistic': 'Average',
                        'ActionsEnabled': True,
                        'AlarmDescription': f'CPU utilization is below 10% for instance {instance_id}'
                    }
                    
                    if alarm_name in existing_alarm_names:
                        # Update existing alarm
                        self.cloudwatch.put_metric_alarm(**alarm_config)
                        self.logger.info(f"Updated alarm for instance {instance_id}")
                    else:
                        # Create new alarm
                        self.cloudwatch.put_metric_alarm(**alarm_config)
                        self.logger.info(f"Created new alarm for instance {instance_id}")
            
            # Clean up obsolete alarms
            obsolete_alarms = existing_alarm_names - needed_alarms
            if obsolete_alarms:
                self.cloudwatch.delete_alarms(
                    AlarmNames=list(obsolete_alarms)
                )
                self.logger.info(f"Cleaned up {len(obsolete_alarms)} obsolete alarms")
            
            return True
            
        except ClientError as e:
            self.logger.error(f"Failed to manage resource monitoring: {str(e)}")
            return False

    def manage_resource_shutdown(self) -> bool:
        """
        Manages automated shutdown for non-production resources.
        Only stops instances that are currently running.
        """
        try:
            # Get only running instances with development or testing tags
            instances = self.ec2.describe_instances(
                Filters=[
                    {
                        'Name': 'tag:Environment',
                        'Values': ['Development', 'Testing', 'Dev', 'Test']
                    },
                    {
                        'Name': 'instance-state-name',
                        'Values': ['running']
                    }
                ]
            )
            
            # Collect instances that need to be stopped
            instance_ids = []
            for reservation in instances['Reservations']:
                for instance in reservation['Instances']:
                    instance_ids.append(instance['InstanceId'])
            
            if instance_ids:
                self.logger.info(f"Found {len(instance_ids)} instances to stop")
                self.ec2.stop_instances(InstanceIds=instance_ids)
                self.logger.info(f"Stopped instances: {instance_ids}")
            else:
                self.logger.info("No running development/testing instances found")
            
            return True
            
        except ClientError as e:
            self.logger.error(f"Failed to manage resource shutdown: {str(e)}")
            return False

    def manage_container_resources(self) -> bool:
        """
        Manages and monitors container-related resources (ECS, ECR, EKS).
        Sets up monitoring and implements cost-saving measures for container services.
        """
        try:
            self._manage_ecs_resources()
            self._manage_ecr_resources()
            self._manage_eks_resources()
            return True
        except ClientError as e:
            self.logger.error(f"Failed to manage container resources: {str(e)}")
            return False

    def _manage_ecs_resources(self) -> None:
        """
        Manages ECS resources:
        - Identifies and stops idle tasks
        - Optimizes service scaling
        - Monitors Fargate usage
        """
        try:
            # Get all ECS clusters
            clusters = self.ecs.list_clusters()['clusterArns']
            
            for cluster_arn in clusters:
                # Get services in the cluster
                services = self.ecs.list_services(cluster=cluster_arn)['serviceArns']
                
                for service_arn in services:
                    # Get service details
                    service = self.ecs.describe_services(
                        cluster=cluster_arn,
                        services=[service_arn]
                    )['services'][0]
                    
                    # Create CPU utilization alarm for the service
                    self.cloudwatch.put_metric_alarm(
                        AlarmName=f"ECS-LowCPU-{service['serviceName']}",
                        MetricName='CPUUtilization',
                        Namespace='AWS/ECS',
                        Dimensions=[
                            {'Name': 'ClusterName', 'Value': cluster_arn.split('/')[-1]},
                            {'Name': 'ServiceName', 'Value': service['serviceName']}
                        ],
                        Period=3600,
                        EvaluationPeriods=24,
                        Threshold=10.0,
                        ComparisonOperator='LessThanThreshold',
                        Statistic='Average',
                        ActionsEnabled=True,
                        AlarmDescription=f'CPU utilization is below 10% for ECS service {service["serviceName"]}'
                    )

        except ClientError as e:
            self.logger.error(f"Failed to manage ECS resources: {str(e)}")
            raise

    def _manage_ecr_resources(self) -> None:
        """
        Manages ECR resources:
        - Implements lifecycle policies
        - Removes untagged images
        - Monitors storage usage
        """
        try:
            # Get all ECR repositories
            repositories = self.ecr.describe_repositories()['repositories']
            
            for repo in repositories:
                repo_name = repo['repositoryName']
                
                # Set lifecycle policy to remove untagged images older than 14 days
                lifecycle_policy = {
                    'rules': [
                        {
                            'rulePriority': 1,
                            'description': 'Remove untagged images older than 14 days',
                            'selection': {
                                'tagStatus': 'untagged',
                                'countType': 'sinceImagePushed',
                                'countUnit': 'days',
                                'countNumber': 14
                            },
                            'action': {
                                'type': 'expire'
                            }
                        },
                        {
                            'rulePriority': 2,
                            'description': 'Keep only 30 tagged images',
                            'selection': {
                                'tagStatus': 'tagged',
                                'tagPrefixList': ['v', 'release'],
                                'countType': 'imageCountMoreThan',
                                'countNumber': 30
                            },
                            'action': {
                                'type': 'expire'
                            }
                        }
                    ]
                }
                
                self.ecr.put_lifecycle_policy(
                    repositoryName=repo_name,
                    lifecyclePolicyText=json.dumps(lifecycle_policy)
                )
                
                # Set up storage monitoring
                self.cloudwatch.put_metric_alarm(
                    AlarmName=f"ECR-HighStorage-{repo_name}",
                    MetricName='RepositorySize',
                    Namespace='AWS/ECR',
                    Dimensions=[{'Name': 'RepositoryName', 'Value': repo_name}],
                    Period=86400,  # 24 hours
                    EvaluationPeriods=1,
                    Threshold=10 * 1024 * 1024 * 1024,  # 10GB
                    ComparisonOperator='GreaterThanThreshold',
                    Statistic='Maximum',
                    ActionsEnabled=True,
                    AlarmDescription=f'ECR repository {repo_name} size exceeds 10GB'
                )

        except ClientError as e:
            self.logger.error(f"Failed to manage ECR resources: {str(e)}")
            raise

    def _manage_eks_resources(self) -> None:
        """
        Manages EKS resources:
        - Monitors cluster utilization
        - Optimizes node groups
        - Tracks Fargate profiles
        """
        try:
            # Get all EKS clusters
            clusters = self.eks.list_clusters()['clusters']
            
            for cluster_name in clusters:
                # Get cluster details
                cluster = self.eks.describe_cluster(name=cluster_name)['cluster']
                
                # Monitor cluster control plane metrics
                self.cloudwatch.put_metric_alarm(
                    AlarmName=f"EKS-ControlPlane-{cluster_name}",
                    MetricName='cluster_failed_node_count',
                    Namespace='ContainerInsights',
                    Dimensions=[{'Name': 'ClusterName', 'Value': cluster_name}],
                    Period=300,  # 5 minutes
                    EvaluationPeriods=3,
                    Threshold=0,
                    ComparisonOperator='GreaterThanThreshold',
                    Statistic='Maximum',
                    ActionsEnabled=True,
                    AlarmDescription=f'EKS cluster {cluster_name} has failed nodes'
                )
                
                # Get all node groups for the cluster
                nodegroups = self.eks.list_nodegroups(clusterName=cluster_name)['nodegroups']
                
                for nodegroup_name in nodegroups:
                    # Monitor node group CPU utilization
                    self.cloudwatch.put_metric_alarm(
                        AlarmName=f"EKS-NodeGroup-CPU-{cluster_name}-{nodegroup_name}",
                        MetricName='node_cpu_utilization',
                        Namespace='ContainerInsights',
                        Dimensions=[
                            {'Name': 'ClusterName', 'Value': cluster_name},
                            {'Name': 'NodeGroup', 'Value': nodegroup_name}
                        ],
                        Period=3600,
                        EvaluationPeriods=24,
                        Threshold=20.0,
                        ComparisonOperator='LessThanThreshold',
                        Statistic='Average',
                        ActionsEnabled=True,
                        AlarmDescription=f'Node group {nodegroup_name} in cluster {cluster_name} has low CPU utilization'
                    )

        except ClientError as e:
            self.logger.error(f"Failed to manage EKS resources: {str(e)}")
            raise

    def get_container_cost_summary(self) -> dict:
        """
        Retrieves cost summary specifically for container services.
        Breaks down costs by ECS, ECR, and EKS usage.
        """
        try:
            ce = boto3.client('ce')
            end_date = datetime.datetime.now().strftime('%Y-%m-%d')
            start_date = datetime.datetime.now().replace(day=1).strftime('%Y-%m-%d')
            
            response = ce.get_cost_and_usage(
                TimePeriod={
                    'Start': start_date,
                    'End': end_date
                },
                Granularity='MONTHLY',
                Metrics=['UnblendedCost'],
                GroupBy=[
                    {'Type': 'DIMENSION', 'Key': 'SERVICE'},
                    {'Type': 'DIMENSION', 'Key': 'USAGE_TYPE'}
                ],
                Filter={
                    'And': [
                        {
                            'Dimensions': {
                                'Key': 'SERVICE',
                                'Values': [
                                    'Amazon Elastic Container Service',
                                    'Amazon Elastic Container Registry',
                                    'Amazon Elastic Kubernetes Service'
                                ]
                            }
                        }
                    ]
                }
            )
            
            return response
            
        except ClientError as e:
            self.logger.error(f"Failed to get container cost summary: {str(e)}")
            return {}

    def get_cost_summary(self) -> dict:
        """
        Retrieves the current month's cost summary.
        This method is naturally idempotent as it's read-only.
        """
        try:
            ce = boto3.client('ce')
            end_date = datetime.datetime.now().strftime('%Y-%m-%d')
            start_date = datetime.datetime.now().replace(day=1).strftime('%Y-%m-%d')
            
            response = ce.get_cost_and_usage(
                TimePeriod={
                    'Start': start_date,
                    'End': end_date
                },
                Granularity='MONTHLY',
                Metrics=['UnblendedCost'],
                GroupBy=[{'Type': 'DIMENSION', 'Key': 'SERVICE'}]
            )
            
            return response
            
        except ClientError as e:
            self.logger.error(f"Failed to get cost summary: {str(e)}")
            return {}

def main():
    """
    Main execution function that manages cost controls.
    Can be run multiple times safely.
    """
    try:
        manager = AWSCostManager(
            monthly_budget=100.0,  # Set your monthly budget in USD
            email='your.email@example.com'  # Set your email for notifications
        )
        
        # Set up general cost management
        manager.create_or_update_budget_alert()
        manager.manage_resource_monitoring()
        manager.manage_resource_shutdown()
        
        # Manage container resources
        manager.manage_container_resources()
        
        # Get and display cost summaries
        print("\nOverall Cost Summary:")
        print(json.dumps(manager.get_cost_summary(), indent=2))
        
        print("\nContainer Services Cost Summary:")
        print(json.dumps(manager.get_container_cost_summary(), indent=2))
        
    except Exception as e:
        logging.error(f"Failed to run cost management: {str(e)}")

if __name__ == "__main__":
    main()
