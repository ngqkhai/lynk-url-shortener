output "instance_id" { value = aws_instance.node.id }
output "public_ip" { value = aws_eip.node.public_ip }
output "artifact_bucket" { value = aws_s3_bucket.artifacts.id }
output "database_backup_bucket" { value = aws_s3_bucket.database_backups.id }
output "instance_role_name" { value = aws_iam_role.node.name }
output "region" { value = "ap-southeast-1" }
output "ssm_document" { value = aws_ssm_document.deploy.name }
