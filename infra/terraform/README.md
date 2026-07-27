# Terraform

```bash
cd infra/terraform
terraform init
terraform plan -var-file=production.tfvars
```

What this does and does not cover:

- **Covers**: managed Postgres (encrypted, multi-AZ in production, 30-day
  backups, deletion protection) and Redis (encrypted in transit and at rest,
  automatic failover). Both private — nothing stateful is internet-reachable.
- **Deliberately not covered**: the VPC and EKS cluster themselves, which are
  usually owned by a platform team and passed in via `private_subnet_ids` and
  `vpc_security_group_ids`. Qdrant is expected as Qdrant Cloud (EU) or a
  StatefulSet; the choice depends on volume and has not been made yet.
- **Region is validated to be EU-only.** MatchIT holds CVs and interview
  transcripts belonging to EU data subjects; a `us-east-1` typo would be a
  transfer, not a deployment detail, so Terraform refuses it outright.
- The master password is managed by AWS Secrets Manager rather than a variable,
  so it never lands in Terraform state.
