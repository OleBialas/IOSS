# Cloud sandboxes

Learners start their own [sandbox](../sandbox/) from a web page. They need only a browser and the access code. Each sandbox is a separate EC2 instance with Forgejo, the seeded tinystats repository and CI.

## How it works

```
Browser ──HTTPS──▶ Lambda Function URL (launcher)
                     │ checks the access code and the limit
                     │ RunInstances from the launch template
                     ▼
                   EC2 instance (Ubuntu 24.04, one per learner)
                     │ user data: installs Docker, downloads the bundle from S3,
                     │ runs sandbox/compose.yaml and sandbox/setup.py
                     ▼
                   Forgejo at http://<public DNS name>:3000/tinystats/tinystats
```

- `launcher/src/app.py`: one Lambda function. It serves the page, starts, shows and ends sessions, and terminates expired sandboxes.
- `launcher/src/user_data.sh`: the boot script of a sandbox instance.
- `launcher/src/index.html`: the web page.
- `terraform/`: the VPC, the launch template, the S3 bundle of `sandbox/` and `seed/`, the DynamoDB session table, the Lambda function and the reaper schedule.

The page polls the launcher. The launcher reports that a sandbox is ready when Forgejo shows all the seeded issues. Then the page shows the repository URL and the password of the user `newcomer`. A sandbox takes about 3–5 minutes to start.

## Deploy

Requirements: Terraform 1.6 or later and AWS credentials that can create the resources above.

```bash
cd cloud/terraform
cp terraform.tfvars.example terraform.tfvars   # set access_code
terraform init
terraform apply
```

Give the output `launcher_url` and the access code to the learners.

Terraform builds the bundle from your working copy of `sandbox/` and `seed/`. After you change them, run `terraform apply` again. New sandboxes use the new bundle.

## Limits and costs

| Setting | Default | Purpose |
| :-- | :-- | :-- |
| `access_code` | none | Only people with the code can start a sandbox. Change it per workshop. |
| `max_sessions` | 10 | Sandboxes that run at the same time. |
| `session_minutes` | 180 | Lifetime of a sandbox. Then the instance is terminated and all work in it is lost. |
| `instance_type` | `m7i-flex.large` | 2 vCPU and 8 GB. Eligible for the AWS Free plan. About 0.09 USD per hour in `eu-north-1`, plus a 30 GB disk. |
| `allowed_cidrs` | `0.0.0.0/0` | Networks that can reach the sandboxes. |

Three mechanisms end a sandbox:

1. The learner selects **End my sandbox now**.
2. The instance schedules its own shutdown at boot. The launch template turns the shutdown into a termination. This works even if the launcher fails.
3. Every 10 minutes the reaper terminates instances after their lifetime.

The launcher, the table and the bucket cost almost nothing when no sandbox runs.

To delete everything: `terraform destroy`. First end all running sandboxes, or terminate the instances with the tag `ioss:managed=true`, because Terraform did not create them.

## Security

- A sandbox is reachable from the internet on port 3000 over plain HTTP. Its passwords are throwaway test passwords. Do not use real credentials in it.
- The learner can push workflows. CI jobs run in a privileged Docker-in-Docker container, so a learner can get root on their own instance. Each learner has their own instance. The instance has no IAM role, and IMDSv2 with a hop limit of 1 keeps containers away from the instance metadata.
- The launcher's IAM role can only start instances from the launch template and terminate instances with the tag `ioss:managed=true`.
- Anyone with the session link in a browser's local storage can see the password of that sandbox.
- The launcher checks the readiness of a sandbox from the internet. If you narrow `allowed_cidrs`, sandboxes stay in "installing" until they fail.

## Debug

The boot script logs to `/var/log/ioss-setup.log` on the instance. The instances have no SSH key. To read the log, use **EC2 → Instance → Actions → Monitor and troubleshoot → Get system log**, or add a key pair to the launch template.

## Test

```bash
cd cloud/launcher
python3 -m pytest tests
```

The tests replace EC2, S3 and DynamoDB with fakes and need only pytest.

## Not done yet

- HTTPS for the sandboxes, for example with Caddy and a DNS name per sandbox
- A mentor view that lists the running sandboxes
- An atomic limit: two requests at the same moment can exceed `max_sessions` by one
