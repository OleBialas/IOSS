variable "region" {
  description = "AWS region for the launcher and the sandboxes"
  type        = string
  default     = "eu-north-1"
}

variable "access_code" {
  description = "Code that learners enter to start a sandbox. Change it per workshop."
  type        = string
  sensitive   = true
  validation {
    condition     = length(var.access_code) >= 8
    error_message = "Use an access code with at least 8 characters."
  }
}

variable "max_sessions" {
  description = "Maximum number of sandboxes that run at the same time"
  type        = number
  default     = 10
}

variable "session_minutes" {
  description = "Lifetime of a sandbox in minutes. Then it is deleted."
  type        = number
  default     = 180
}

variable "instance_type" {
  description = "EC2 instance type of a sandbox. Forgejo, Docker-in-Docker and CI jobs need about 4 GB of memory."
  type        = string
  default     = "m7i-flex.large"
}

variable "volume_size" {
  description = "Disk size of a sandbox in GB"
  type        = number
  default     = 30
}

variable "allowed_cidrs" {
  description = "Networks that can reach the sandboxes. The launcher must reach them too, to check that they are ready."
  type        = list(string)
  default     = ["0.0.0.0/0"]
}

variable "name_prefix" {
  description = "Prefix for the names of all resources"
  type        = string
  default     = "ioss"
}
