import logging
import random
from typing import List

import dacite
import httpx
import requests

import dagshub
from dagshub.auth.token_auth import HTTPBearerAuth
from dagshub.common import config
from dagshub.common.api.responses import ContentAPIEntry
from dagshub.common.helpers import prompt_user
from dagshub.common.util import lazy_load
from dagshub.data_engine.model import datasources
from dagshub.data_engine.model.errors import DatasourceAlreadyExistsError
from dagshub.data_engine.voxel_plugin_server.server import run_plugin_server

logger = logging.getLogger(__name__)

fo = lazy_load("fiftyone")
IPython = lazy_load("IPython")


class DESnippetDriver:

    def __init__(self, repo="kirill/baby-yoda-segmentation-dataset"):
        self.repo = repo
        self.host = config.host
        self.datasource_name = "default-dataset"
        self.dataset = self.init_dataset()
        auth = HTTPBearerAuth(dagshub.auth.get_token(host=self.host))
        self.client = httpx.Client(auth=auth)

    def init_dataset(self):
        try:
            ds = datasources.create_from_repo(self.repo, self.datasource_name, "/images")
        except DatasourceAlreadyExistsError:
            ds = datasources.get_datasource(self.repo, self.datasource_name)
        return ds

    # def create_datasource(self):
    #     # TODO: make prettier actually :)
    #     self.dataset.source.client.create_datasource("Test-bucket", self.bucket_url)

    # def add_metadata(self):
    #     files = ["file1", "file2"]
    #     with self.dataset.metadata_context() as ctx:
    #         ctx.update_metadata(files, {"episode": 2})
    #
    # def add_more_metadata(self):
    #     with self.dataset.metadata_context() as ctx:
    #         ctx.update_metadata("file1", {"air_date": "2022-01-01"})
    #         ctx.update_metadata("file2", {"air_date": "2022-01-08"})
    #         ctx.update_metadata("file1", {"has_baby_yoda": True})

    def query(self):
        # res = self.dataset.and_query(img_number_ge=5).or_query(img_number_eq=0).peek()
        ds = self.dataset
        q1 = (ds["episode"] > 5) & (ds["episode"] > 5)
        q2 = (ds["episode"] == 1) & (ds["episode"] == 1)
        res = ds[q1 | q2].all()
        # res = ds.or_query(episode_eq=2).peek()
        print(res.dataframe)

    def get_file_list(self, path):
        path = self.dataset.source.content_path(path)
        resp = self.client.get(path)
        return [dacite.from_dict(ContentAPIEntry, e) for e in resp.json()]

    def add_files_with_metadata(self, entries: List[ContentAPIEntry]):
        logger.info("Adding files")

        # Download random words for keys
        word_site = "https://www.mit.edu/~ecprice/wordlist.10000"
        response = requests.get(word_site)
        WORDS = response.content.decode("utf-8").splitlines()

        with self.dataset.metadata_context() as ctx:
            for entry in entries:
                filename = entry.path.split("/")[-1]
                img_num = int(filename.removesuffix(".png"))
                episode_num = img_num % 10 + 1

                meta_dict = {
                    "episode": episode_num
                }
                for i in range(15):
                    key = f"key_{random.randint(1, 10)}"
                    val = random.choice(WORDS)
                    meta_dict[key] = val

                ctx.update_metadata(entry.path, meta_dict)

    def make_voxel(self):
        logger.info("Importing to voxel51")
        # v51_ds = self.dataset.and_query(episode_eq=1).or_query(episode_ge=5).to_voxel51_dataset()
        ds = self.dataset
        # TODO: don't need redundant ands once the gql query actually works
        q1 = (ds["episode"] > 5) & (ds["episode"] > 5)
        q2 = (ds["episode"] == 1) & (ds["episode"] == 1)
        v51_ds = ds[ds["size"] < 1000000].to_voxel51_dataset()

        sess = fo.launch_app(v51_ds)
        IPython.embed()
        sess.wait()


def dataset_create_flow():
    snippet_driver = DESnippetDriver()

    # TO ADD FILES WITH METADATA. DO NOT REPEAT!!
    files = snippet_driver.get_file_list("images")
    snippet_driver.add_files_with_metadata(files)

    # QUERY TEST
    # snippet_driver.query()

    # TO CREATE THE VOXEL APP
    snippet_driver.make_voxel()


def show_voxel():
    snippet_driver = DESnippetDriver()
    snippet_driver.make_voxel()


def just_debugging_voxel():
    ds = fo.load_dataset("my-data")
    plugin_server = run_plugin_server(ds)
    # sess = fo.launch_app(ds)

    # NVM this doesn't work
    # fcse.DagshubLabelstudio = DagshubLabelstudio
    # setattr(sys.modules[fcse.Event.__module__], DagshubLabelstudio.__name__, DagshubLabelstudio)
    # sess._client.add_event_listener("event", fiftyone_handler)

    # sess.wait()

    input("Press enter to exit")

    plugin_server.stop()


def query_debugging():
    snippet_driver = DESnippetDriver()
    snippet_driver.query()


def get_all_datasources(repo="simon/baby-yoda-segmentation-dataset"):
    sources = datasources.get_datasources(repo)
    print(f"Data sources in repo {repo}:")
    for ds in sources:
        print(f"\t{ds.source}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    show_voxel()
    # query_debugging()
    # just_debugging_voxel()
    # dataset_create_flow()
    # get_all_datasources()
