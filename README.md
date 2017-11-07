# opsdroid skill hello

A skill for [opsdroid](https://github.com/opsdroid/opsdroid) to check the total file size in Slack againt the limit and migrate files to S3 if it's over the limit.

## Requirements

- Slack
- An S3 bucket

## Configuration

```yaml
  - name: slack-to-s3
    # Required
    aws_access_key_id: "AWSACCESSKEY"
    aws_secret_access_key: "AWSSECRETKEY"
    slack_api_token: "SLACKTOKEN"
    s3_region_name: 'us-west-2'
    s3_bucket: 'my-slack-files'
    max_total_file_size: 2000000000  # Limit in bytes for Slack files before migrating
    # Optional
    s3_prefix: 'my/slack/files'
    room: '#random'  # Room to notify in
    file_size_buffer: 5250000  # Move extra files to give a buffer before hitting the limit again
```

## Usage

#### `check slack file quota`

Runs the check.

_This also runs daily at 10am via cron_.

> user: check slack file quota
>
> opsdroid: You were getting close to your Slack file limit so I've moved 3 files to the my-slack-files bucket on S3 saving 10MiB.
