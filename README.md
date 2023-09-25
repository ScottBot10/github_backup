# GitHub backup script
Backs up GitHub data for multiple users by using GitHub's [migration API](https://docs.github.com/en/rest/migrations/users). Probably won't work to back up organisations.

## Usage
This script requires Python 3. 

If you want to use config in yaml, you will need the [PyYAML](https://pypi.org/project/PyYAML/) library. You can install it like this:
```shell
pip install PyYAML
```
If you are using the `PyYAML` library and want to use the `!ENV` constructor with a `.env` file you will need to install the `python-dotenv` module:
```shell
pip install python-dotenv
```
To run the script run:
```shell
python github_backup.py
```
or
```shell
python github_backup.py /path/to/config.yml
```
### Config
Config can be in either a YAML or a json format. Use the `CONFIG` variable near the top of the script to embed config into the script. If you do so, other sources of config will be ignored.

yaml:
```yaml
logging:
  version: 1
  formatters:
    brief:
      format: '%(levelname)s:%(message)s'
    precise:
      format: '%(levelname)s:%(asctime)s:%(name)s:%(threadName)s:%(message)s'
  handlers:
    console:
      class: logging.StreamHandler
      level: INFO
      formatter: brief
      stream: ext://sys.stdout
    file:
      class: logging.FileHandler
      level: DEBUG
      formatter: precise
      filename: backup.log
      encoding: utf-8
  loggers:
    github_backup:
      level: DEBUG
      handlers: [console, file]
global:
  outfile: "./backups/{username}/{datetime:%d%m%y_%H%M%S}.tar.gz"
users:
  - token: !ENV GH_TOKEN
    check_time: 10
  - token: ghp_*************************************
    outfile: "/other/location/{username}.tar.gz"
    exclude_git_data: True
```
json:
```json
{
  "logging": {
    "version": 1,
    "formatters": {
      "brief": {
        "format": "%(levelname)s:%(message)s"
      },
      "precise": {
        "format": "%(levelname)s:%(asctime)s:%(name)s:%(threadName)s:%(message)s"
      }
    },
    "handlers": {
      "console": {
        "class": "logging.StreamHandler",
        "level": "INFO",
        "formatter": "brief",
        "stream": "ext://sys.stdout"
      },
      "file": {
        "class": "logging.FileHandler",
        "level": "DEBUG",
        "formatter": "precise",
        "filename": "backup.log"
      }
    },
    "loggers": {
      "github_backup": {
        "level": "DEBUG",
        "handlers": [
          "console",
          "file"
        ]
      }
    }
  },
  "global": {
    "outfile": "./backups/{username}/{datetime:%Y-%m-%dT%H%M%S}.tar.gz"
  },
  "users": [
    {
      "token": "ghp_*************************************"
    },
    {
      "token": "ghp_*************************************",
      "outfile": "/other/location/{username}.tar.gz",
      "exclude_git_data": true
    }
  ]
}
```
The `global` section will apply to every user, but you can override the values
for individual users. You can use the `!ENV` constructor in the YAML config to reference environment variables.

#### User
The config for each user is in a list under the `users` key. For each user, the following options can be used:

- `token` - Your GitHub [personal access token](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens). Cannot go in `global`. ***Required***
- `outfile` - The file name to save the backup as, including the `.tar.gz`. Can use formatting syntax including: `{username}`, `{datetime}` (of backup finish; see [format codes](https://docs.python.org/3/library/datetime.html#strftime-and-strptime-behavior)) and `{id}` (of backup). If it is set to None, then the script will not download the backup. It will still check its state.
- `check_time` - How long to wait inbetween checking the state of the backup in seconds. If it is set to None, the script won't query the state of the backup and so won't automatically download it. Default: `30`
- `affiliation` - Comma separated values. Options: `owner`, `collaborator` and `organization_member`. Default: `owner`
- `visibility` - Limits repositories to back up to ones with a certain visibility. Options: `all`, `public`, `private`. Default: `all`
- `exclude_repos` - A string or list of strings that are the full names (`username/repo_name`) of repositories that you don't want to back up.
- `lock_repositories` - Lock the repositories being backed up. Default: `False`
- `exclude_metadata` - Whether metadata, such as __, should be excluded. Default: `False`
- `exclude_git_data` - Whether the repositories' git data should be excluded. Default: `False`
- `exclude_attachments` - Do not include attachments. Default: `False`
- `exclude_releases` - Do not include releases. Default: `False`
- `exclude_owner_projects` - Whether projects owned by the user should be excluded. Default: `False`
- `org_metadata_only` - Whether the backup should only include metadata (will ignore the exclude flags.). Default: `False`

#### Logging
This script uses Python's [logging](https://docs.python.org/3/library/logging.html) module to log output. You can add logging config under the `logging` key using the [dictConfig() schema](https://docs.python.org/3/library/logging.config.html#configuration-dictionary-schema). The variable, `LOGGER_NAME`, at the top of the script will be used as the name of the logger (default `'github_backup'`), so make sure to have the same name in the `loggers` part of your config.