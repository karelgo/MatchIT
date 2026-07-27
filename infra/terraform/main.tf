# MatchIT infrastructure, EU-only.
#
# Data residency is a product requirement, not a preference: profiles, CVs and
# interview transcripts are personal data belonging to EU subjects, so every
# stateful service is pinned to an EU region and nothing is replicated out.

terraform {
  required_version = ">= 1.6"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

variable "region" {
  description = "EU region. Changing this moves personal data — see docs/architecture.md."
  type        = string
  default     = "eu-west-1"

  validation {
    condition     = startswith(var.region, "eu-")
    error_message = "MatchIT stores EU personal data; the region must be an EU region."
  }
}

variable "environment" {
  type    = string
  default = "production"
}

variable "db_instance_class" {
  type    = string
  default = "db.t4g.medium"
}

provider "aws" {
  region = var.region
}

locals {
  name = "matchit-${var.environment}"
  tags = {
    Project     = "MatchIT"
    Environment = var.environment
    ManagedBy   = "terraform"
  }
}

resource "aws_db_subnet_group" "postgres" {
  name       = "${local.name}-postgres"
  subnet_ids = var.private_subnet_ids
  tags       = local.tags
}

variable "private_subnet_ids" {
  description = "Private subnets for stateful services. No public subnets: nothing stateful is internet-reachable."
  type        = list(string)
}

variable "vpc_security_group_ids" {
  type = list(string)
}

resource "aws_db_instance" "postgres" {
  identifier     = "${local.name}-postgres"
  engine         = "postgres"
  engine_version = "16"
  instance_class = var.db_instance_class

  allocated_storage     = 100
  max_allocated_storage = 1000
  storage_encrypted     = true

  db_name  = "matchit"
  username = "matchit"
  # Rotated by Secrets Manager; never rendered into state by a literal.
  manage_master_user_password = true

  db_subnet_group_name   = aws_db_subnet_group.postgres.name
  vpc_security_group_ids = var.vpc_security_group_ids
  publicly_accessible    = false

  multi_az                = var.environment == "production"
  backup_retention_period = 30
  deletion_protection     = var.environment == "production"
  skip_final_snapshot     = var.environment != "production"

  performance_insights_enabled = true
  tags                         = local.tags
}

resource "aws_elasticache_replication_group" "redis" {
  replication_group_id = "${local.name}-redis"
  description          = "Rate limits, chat pub/sub and AI usage counters"
  engine               = "redis"
  engine_version       = "7.1"
  node_type            = "cache.t4g.small"
  num_cache_clusters   = 2

  at_rest_encryption_enabled = true
  transit_encryption_enabled = true
  automatic_failover_enabled = true

  subnet_group_name  = aws_elasticache_subnet_group.redis.name
  security_group_ids = var.vpc_security_group_ids
  tags               = local.tags
}

resource "aws_elasticache_subnet_group" "redis" {
  name       = "${local.name}-redis"
  subnet_ids = var.private_subnet_ids
}

output "database_endpoint" {
  value     = aws_db_instance.postgres.endpoint
  sensitive = true
}

output "redis_endpoint" {
  value     = aws_elasticache_replication_group.redis.primary_endpoint_address
  sensitive = true
}
