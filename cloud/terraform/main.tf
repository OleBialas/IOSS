terraform {
  required_version = ">= 1.6"
  required_providers {
    aws = {
      source = "hashicorp/aws"
      # Recent 6.x versions add both Function URL permissions automatically.
      version = "~> 6.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.4"
    }
  }
}

provider "aws" {
  region = var.region
  default_tags {
    tags = { Project = "ioss" }
  }
}

data "aws_caller_identity" "current" {}
data "aws_availability_zones" "available" { state = "available" }

locals {
  repo_root = abspath("${path.module}/../..")
  account   = data.aws_caller_identity.current.account_id
  ec2_arn   = "arn:aws:ec2:${var.region}:${local.account}"

  # What a sandbox instance needs from this repository.
  bundle_files = [
    for f in fileset(local.repo_root, "{sandbox,seed}/**") : f
    if !startswith(basename(f), ".env") && !strcontains(f, "__pycache__")
  ]
  # setup.py creates the seed issues, then the quest issue. When all of them
  # exist, the sandbox is ready.
  seed_issues = length(fileset(local.repo_root, "seed/issues/*.md")) + 1
}

# --- Network --------------------------------------------------------------

resource "aws_vpc" "this" {
  cidr_block = "10.42.0.0/16"
  # Instances need a public DNS name. Inside the VPC it resolves to the
  # private IP, which lets CI jobs reach Forgejo at its ROOT_URL.
  enable_dns_support   = true
  enable_dns_hostnames = true
  tags                 = { Name = "${var.name_prefix}-vpc" }
}

resource "aws_internet_gateway" "this" {
  vpc_id = aws_vpc.this.id
}

resource "aws_subnet" "public" {
  vpc_id                  = aws_vpc.this.id
  cidr_block              = "10.42.0.0/20"
  availability_zone       = data.aws_availability_zones.available.names[0]
  map_public_ip_on_launch = true
  tags                    = { Name = "${var.name_prefix}-public" }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.this.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.this.id
  }
}

resource "aws_route_table_association" "public" {
  subnet_id      = aws_subnet.public.id
  route_table_id = aws_route_table.public.id
}

resource "aws_security_group" "sandbox" {
  name        = "${var.name_prefix}-sandbox"
  description = "IOSS sandbox: Forgejo web UI and Git over HTTP"
  vpc_id      = aws_vpc.this.id

  ingress {
    description = "Forgejo"
    from_port   = 3000
    to_port     = 3000
    protocol    = "tcp"
    cidr_blocks = var.allowed_cidrs
  }

  egress {
    description = "Packages, images, GitHub and CI downloads"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# --- Sandbox instances ----------------------------------------------------

data "aws_ssm_parameter" "ubuntu" {
  name = "/aws/service/canonical/ubuntu/server/24.04/stable/current/amd64/hvm/ebs-gp3/ami-id"
}

resource "aws_launch_template" "sandbox" {
  name                   = "${var.name_prefix}-sandbox"
  image_id               = data.aws_ssm_parameter.ubuntu.insecure_value
  instance_type          = var.instance_type
  update_default_version = true

  # The boot script schedules a shutdown at the end of the session.
  instance_initiated_shutdown_behavior = "terminate"

  network_interfaces {
    associate_public_ip_address = true
    subnet_id                   = aws_subnet.public.id
    security_groups             = [aws_security_group.sandbox.id]
    delete_on_termination       = true
  }

  # IMDSv2 only, and a hop limit of 1, so containers (and CI jobs) cannot
  # read the instance metadata. The instance has no IAM role anyway.
  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 1
  }

  block_device_mappings {
    device_name = "/dev/sda1"
    ebs {
      volume_size           = var.volume_size
      volume_type           = "gp3"
      encrypted             = true
      delete_on_termination = true
    }
  }
}

# --- Sandbox bundle -------------------------------------------------------

resource "aws_s3_bucket" "bundle" {
  bucket_prefix = "${var.name_prefix}-bundle-"
  force_destroy = true
}

resource "aws_s3_bucket_public_access_block" "bundle" {
  bucket                  = aws_s3_bucket.bundle.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

data "archive_file" "bundle" {
  type        = "zip"
  output_path = "${path.module}/build/bundle.zip"

  dynamic "source" {
    for_each = local.bundle_files
    content {
      content  = file("${local.repo_root}/${source.value}")
      filename = source.value
    }
  }
}

resource "aws_s3_object" "bundle" {
  bucket = aws_s3_bucket.bundle.id
  key    = "bundle-${data.archive_file.bundle.output_md5}.zip"
  source = data.archive_file.bundle.output_path
}

# --- Sessions -------------------------------------------------------------

resource "aws_dynamodb_table" "sessions" {
  name         = "${var.name_prefix}-sessions"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "session_id"

  attribute {
    name = "session_id"
    type = "S"
  }

  ttl {
    attribute_name = "ttl"
    enabled        = true
  }
}
