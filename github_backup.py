import json
import logging
import logging.config
import os
import shutil
import threading
import time
from datetime import datetime
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import urlopen, Request

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

# Add config here to use instead of the external file.
# If you do, only this config will be used.
CONFIG = """

"""
DEFAULT_CONFIG_FILE = "config.yml"
LOGGER_NAME = "github_backup"

API = "https://api.github.com"
HEADERS = {"Accept": "application/vnd.github+json"}


def request(url, logger, params=None, headers=None, json_data=None):
    if params:
        url += "?" + urlencode(params)
    if headers is None:
        headers = {}
    if json_data is not None:
        json_data = json.dumps(json_data).encode("utf-8")
        headers = dict(**headers, **{"Content-Type": "application/json"})

    try:
        with urlopen(Request(url, headers=headers, data=json_data)) as r:
            return json.loads(r.read())
    except HTTPError as e:
        logger.exception(f"{e.__class__.__qualname__} {url=} {params=} {headers=} {json_data=} {e.fp.read()=}")
    except Exception as e:
        logger.exception(f"{e.__class__.__qualname__} {url=} {params=} {headers=} {json_data=}")


# try to use the PyYAML library. If it is not available, use the json library
try:
    import yaml as _yaml


    class YAMLLoader(_yaml.SafeLoader):
        @staticmethod
        def _env_var_constructor(loader, node):
            """
            Constructor for inserting the values of environment variable to a yaml file.
            Can either be a string or a list of length two
            with the first value being the name of the environment variable
            and the second being a default value for if the variable doesn't exist.
            """

            default = None

            if node.id == 'scalar':
                key = str(loader.construct_scalar(node))
            else:
                seq = loader.construct_sequence(node)

                if len(seq) > 1:
                    key = seq[0]
                    default = seq[1]
                else:
                    key = seq[0]

            return os.getenv(key, default)

        def __init__(self, stream):
            super().__init__(stream)
            self.add_constructor("!ENV", self._env_var_constructor)
            self.add_constructor("!env", self._env_var_constructor)


    def load_string(s):
        return _yaml.load(s, YAMLLoader)


    load_file = load_string
except ImportError:
    def load_string(s):
        return json.loads(s)


    def load_file(f):
        return json.load(f)


class User:
    """
    Class representing a user that has a token. Encapsulates all the data of a user to easily pass to a thread.
    """

    def __init__(self, global_config: dict, user_config: dict, logger: logging.Logger):
        self.logger = logger

        self.token = user_config.get('token')
        if self.token is None:
            raise ValueError('token is required')

        self.outfile = self._config_val('outfile', None, global_config, user_config)
        self.check_time = self._config_val('check_time', 30, global_config, user_config)
        self.affiliation = self._config_val('affiliation', 'owner', global_config, user_config)
        self.visibility = self._config_val('visibility', 'all', global_config, user_config)
        self.exclude_repos = self._config_val('exclude_repos', set(), global_config, user_config)
        if isinstance(self.exclude_repos, str):
            self.exclude_repos = {self.exclude_repos}
        self.lock_repositories = self._config_val('lock_repositories', False, global_config, user_config)
        self.exclude_metadata = self._config_val('exclude_metadata', False, global_config, user_config)
        self.exclude_git_data = self._config_val('exclude_git_data', False, global_config, user_config)
        self.exclude_attachments = self._config_val('exclude_attachments', False, global_config, user_config)
        self.exclude_releases = self._config_val('exclude_releases', False, global_config, user_config)
        self.exclude_projects = self._config_val('exclude_owner_projects', False, global_config, user_config)
        self.org_metadata_only = self._config_val('org_metadata_only', False, global_config, user_config)

        self.auth_headers = [("Authorization", f"Bearer {self.token}")]
        self.headers = dict(**HEADERS, **dict(self.auth_headers))

        self.repos = list(self.get_repos()) if not self.org_metadata_only else []
        self.id, self.username = self.start_migration()

    @staticmethod
    def _config_val(var, default, global_config, user_config):
        if var in user_config:
            return user_config[var]
        elif var in global_config:
            return global_config[var]
        else:
            return default

    def get_repos(self):
        js = request(f"{API}/user/repos", self.logger, headers=self.headers, params={
            'affiliation': self.affiliation,
            'visibility': self.visibility
        })
        self.logger.debug(f"Got repository info")
        return {repo.get('full_name') for repo in js} - self.exclude_repos

    def start_migration(self):
        data = {
            "repositories": self.repos,
            "lock_repositories": self.lock_repositories,
            "exclude_metadata": self.exclude_metadata,
            "exclude_git_data": self.exclude_git_data,
            "exclude_attachments": self.exclude_attachments,
            "exclude_releases": self.exclude_attachments,
            "exclude_owner_projects": self.exclude_projects
        }
        if self.org_metadata_only:
            data["org_metadata_only"] = self.org_metadata_only
        js = request(f"{API}/user/migrations", self.logger, headers=self.headers, json_data=data)
        mid, name = js["id"], js["owner"]["login"]
        self.logger.info(f"Started backup {mid} for user: {name}")
        return mid, name

    def get_state(self):
        js = request(f"{API}/user/migrations/{self.id}", self.logger, headers=self.headers)
        state = js.get('state')
        self.logger.debug(f"Got state: '{state}'")
        return state, js.get('updated_at')

    def check(self):
        self.logger.info(f"Waiting for {self.username}'s backup to complete...")
        while True:
            time.sleep(self.check_time)
            state, dt = self.get_state()
            if state == "exported":
                self.logger.info(f"Backup for {self.username} created")
                if self.outfile is not None:
                    dt = datetime.strptime(dt, "%Y-%m-%dT%H:%M:%S.%f%z")
                    self.save_backup(dt)
                break
            elif state == "failed":
                self.logger.error(f"Backup for {self.username} failed!")
                break

    def save_backup(self, dt):
        filename = self.outfile.format(**{
            "username": self.username,
            "datetime": dt,
            "id": self.id
        })
        dirname = os.path.dirname(filename)
        self.logger.debug(f"Downloading {self.username}'s backup to {filename}")
        if not os.path.isdir(dirname):
            self.logger.debug(f"Creating path: {dirname}")
            os.makedirs(dirname)
        url = f"{API}/user/migrations/{self.id}/archive"
        try:
            req = Request(url)
            # The requests gets redirected to an AWS S3 endpoint, and it gives an error if the GitHub authorization
            # headers are also redirected so unredirected headers are needed.
            for key, val in self.auth_headers:
                req.add_unredirected_header(key, val)
            with urlopen(req) as r, open(filename, 'wb') as f:
                shutil.copyfileobj(r, f)

        except HTTPError as e:
            self.logger.exception(f"{e.__class__.__qualname__} {url=} {self.auth_headers=} "
                                  f"{e.fp.headers=} {e.fp.read()=}")
        except Exception as e:
            self.logger.exception(f"{e.__class__.__qualname__} {url=} {self.auth_headers=}")
        else:
            self.logger.info(f"Saved backup for {self.username}")


def main(args):
    if CONFIG.strip():  # If the config variable is empty
        config = load_string(CONFIG)
    else:
        config_file = args[0] if args else DEFAULT_CONFIG_FILE
        with open(config_file) as f:
            config = load_file(f)
    global_config = config.get('global', {})
    logging_config = config.get('logging')

    if logging_config is not None:
        logging.config.dictConfig(logging_config)
    logger = logging.getLogger(LOGGER_NAME)
    logger.debug('Logger initialized')

    users = [User(global_config, user_config, logger) for user_config in config['users']]
    threads = []
    for user in users:
        if user.check_time > 0:
            thread = threading.Thread(target=User.check, args=(user,))
            threads.append(thread)
            thread.start()

    for thread in threads:
        thread.join()


if __name__ == "__main__":
    import sys

    main(sys.argv[1:])
