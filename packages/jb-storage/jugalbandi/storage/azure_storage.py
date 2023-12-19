from typing import AsyncIterator
import os
import logging
from azure.storage.blob.aio import BlobServiceClient
from azure.core.exceptions import ResourceNotFoundError
from azure.identity.aio import DefaultAzureCredential
from .storage import Storage
from tenacity import (
    retry,
    wait_random_exponential,
    after_log,
    retry_if_not_exception_type,
)

logger = logging.getLogger(__name__)

class AzureStorage(Storage):
    def __init__(self, account_url: str, container_name: str, base_path: str):
        self.account_url = account_url
        self.container_name = container_name
        self.base_path = base_path
        self.client = BlobServiceClient(account_url=self.account_url, credential=DefaultAzureCredential())

    async def write_file(self, file_path: str, content: bytes):
        blob_name = f"{self.base_path}/{file_path}"
        blob_client = self.client.get_blob_client(self.container_name, blob_name)
        await blob_client.upload_blob(content, overwrite=True)

    @retry(
        wait=wait_random_exponential(multiplier=1, max=60),
        retry=retry_if_not_exception_type(ResourceNotFoundError),
    )
    
    async def read_file(self, file_path: str) -> bytes:
        blob_name = f"{self.base_path}/{file_path}"
        blob_client = self.client.get_blob_client(self.container_name, blob_name)
        try:
            download_stream = await blob_client.download_blob()
            return await download_stream.readall()
        except ResourceNotFoundError:
            raise FileNotFoundError(f"file {file_path} not found")

    def path(self, path_suffix: str):
        return f"azure://{self.container_name}/{self._relative_path(path_suffix)}"

    async def list_files(self, folder_path: str) -> AsyncIterator[str]:
        prefix = f"{self._relative_path(folder_path)}/"
        blob_list = self.client.get_container_client(self.container_name).list_blobs(name_starts_with=prefix)
        async for blob in blob_list:
            yield blob.name[len(prefix):]

    async def file_exists(self, file_path: str) -> bool:
        blob_name = f"{self.base_path}/{file_path}"
        blob_client = self.client.get_blob_client(self.container_name, blob_name)
        return await blob_client.exists()

    def new_store(self, folder_suffix: str) -> "AzureStorage":
        folder_path = self._relative_path(folder_suffix)
        return AzureStorage(self.connection_string, self.container_name, folder_path)

    async def remove_file(self, file_path: str):
        full_file_path = self._relative_path(file_path)
        blob_client = self.client.get_blob_client(self.container_name, full_file_path)
        await blob_client.delete_blob()

    async def list_all_files(self, folder_path: str):
        prefix = f"{self._relative_path(folder_path)}/"
        blob_list = self.client.get_container_client(self.container_name).list_blobs(name_starts_with=prefix)
        async for blob in blob_list:
            yield blob.name[len(prefix):]

    async def make_public(self, file_path: str) -> str:
        blob_name = f"{self.base_path}/{file_path}"
        blob_client = self.client.get_blob_client(self.container_name, blob_name)

        sas_token = generate_blob_sas(
            account_name=self.client.account_name,
            container_name=self.container_name,
            blob_name=blob_name,
            account_key=self.client.credential.account_key,
            permission=BlobSasPermissions(read=True),
            expiry=datetime.utcnow() + timedelta(days=365)
        )

        return f"{blob_client.url}?{sas_token}"
    
    async def public_url(self, file_path: str) -> str:
        blob_name = f"{self.base_path}/{file_path}"
        blob_client = self.client.get_blob_client(self.container_name, blob_name)

        sas_token = generate_blob_sas(
            account_name=self.client.account_name,
            container_name=self.container_name,
            blob_name=blob_name,
            account_key=self.client.credential.account_key,
            permission=BlobSasPermissions(read=True),
            expiry=datetime.utcnow() + timedelta(minutes=5)
        )

        return f"{blob_client.url}?{sas_token}"

    async def copy_file(self, file_path: str, target_container: str, target_file_path: str):
        source_blob = f"{self.base_path}/{file_path}"
        source_blob_client = self.client.get_blob_client(self.container_name, source_blob)
        target_blob_client = self.client.get_blob_client(target_container, target_file_path)
        copy_source_url = source_blob_client.url
        await target_blob_client.start_copy_from_url(copy_source_url)

    @classmethod
    def new_azure_file_adapter(cls, connection_string: str, base_path: str) -> "AzureStorage":
        new_base_path = base_path[7:]
        path_elements = new_base_path.split("/", 1)
        container_name = path_elements[0]
        folder_path = ""
        if len(path_elements) > 1:
            folder_path = path_elements[1]
        return cls(connection_string, container_name, folder_path)