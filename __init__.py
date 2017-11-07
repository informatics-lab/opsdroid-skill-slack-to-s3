import logging
import random

import aiobotocore
import aiohttp

from opsdroid.matchers import match_crontab, match_regex
from opsdroid.message import Message


_LOGGER = logging.getLogger(__name__)


################################################################################
# Helper functions                                                             #
################################################################################


def human_bytes(num, suffix='B'):
    """Returns a string of human readable file size."""
    for unit in ['','Ki','Mi','Gi','Ti','Pi','Ei','Zi']:
        if abs(num) < 1024.0:
            return "%3.1f%s%s" % (num, unit, suffix)
        num /= 1024.0
    return "%.1f%s%s" % (num, 'Yi', suffix)


async def count_total_file_size(files):
    """Counts the total size of a list of slack files."""
    total_file_size = 0
    for file in files:
        total_file_size = total_file_size + file["size"]
    return total_file_size


async def download_file(slack_api_token, file):
    """Downloads a file from slack into memory and returns the raw bytes."""
    headers = {'Authorization': 'Bearer {}'.format(slack_api_token)}
    async with aiohttp.ClientSession() as session:
        async with session.get(file["url_private"], headers=headers) as resp:
            return await resp.read()


async def upload_file(client, file, data, bucket, prefix):
    """Uploads an array of raw bytes to S3 as an object."""
    filename = "{}-{}".format(file["id"], file["name"])
    resp = await client.put_object(Bucket=bucket,
                                   Key="{}/{}".format(prefix, filename),
                                   Body=data)
    if resp["ResponseMetadata"]["HTTPStatusCode"] == 200:
        return True
    return False


async def cleanup_file(slack_api_token, file):
    """Deletes a file from Slack."""
    headers = {"Authorization": "Bearer {}".format(slack_api_token)}
    data = {"file": file["id"]}
    async with aiohttp.ClientSession() as session:
        async with session.post('https://slack.com/api/files.delete', headers=headers, data=data) as resp:
            if resp.status == 200:
                return True
            return False


async def get_file_list(slack_api_token):
    """Gets a list of all files in a slack account."""
    all_files = []
    total_files = 0
    page = 1
    pages = None
    async with aiohttp.ClientSession() as session:
        while pages is None or page <= pages:
            async with session.get('https://slack.com/api/files.list?token={}&page={}'.format(slack_api_token, page)) as resp:
                if resp.status != 200:
                    _LOGGER.error("Bad response from slack api: %s", resp.status)
                files = await resp.json()
                _LOGGER.debug(files)
                pages = files["paging"]["pages"]
                all_files = all_files + files["files"]
                total_files = total_files + len(files["files"])
                page = page + 1
    return all_files


################################################################################
# Skills                                                                       #
################################################################################


@match_crontab("0 10 * * *")
@match_regex(r'check slack file quota', case_sensitive=False)
async def check_slack_file_quota(opsdroid, config, message):
    try:
        aws_access_key_id = config["aws_access_key_id"]
        aws_secret_access_key = config["aws_secret_access_key"]
        slack_api_token = config["slack_api_token"]
        s3_region_name = config["s3_region_name"]
        max_total_file_size = config["max_total_file_size"]
        s3_bucket = config["s3_bucket"]
        s3_prefix = config.get("s3_prefix", "")
        file_size_buffer = config.get("file_size_buffer", 0)
    except KeyError:
        _LOGGER.error("Missing config item(s) in skill %s.",
                      config.get('name', 'aws-tag-compliance'))
        return

    if message is None:
        message = Message("",
                          None,
                          config.get("room", connector.default_room),
                          opsdroid.default_connector)

    files_removed = 0
    data_saved = 0

    files = await get_file_list(slack_api_token)
    size_threshold = max_total_file_size
    while await count_total_file_size(files) > size_threshold:
        if size_threshold == max_total_file_size:
            size_threshold = max_total_file_size - file_size_buffer
        session = aiobotocore.get_session()
        async with session.create_client('s3', region_name=s3_region_name,
                                         aws_secret_access_key=aws_secret_access_key,
                                         aws_access_key_id=aws_access_key_id) as client:
            data = await download_file(slack_api_token, files[-1])
            if await upload_file(client, files[-1], data, s3_bucket, s3_prefix):
                if await cleanup_file(slack_api_token, files[-1]):
                    _LOGGER.debug("Uploaded %s to S3", files[-1]["name"])
                    files_removed = files_removed + 1
                    data_saved = data_saved + files[-1]["size"]
                    files.remove(files[-1])
                else:
                    _LOGGER.debug("%s uploaded to S3 but failed to clean up on Slack", files[-1]["name"])
            else:
                _LOGGER.debug("Upload of %s failed", files[-1]["name"])
    if files_removed > 0:
        await message.respond("You were getting close to your Slack file limit so I've moved {} files to the {} bucket on S3 saving {}.".format(files_removed, s3_bucket, human_bytes(data_saved)))
    else:
        if message.regex:
            await message.respond("Nothing to do, file size is {} and quota is {}".format(
                human_bytes(await count_total_file_size(files)), human_bytes(max_total_file_size)))
