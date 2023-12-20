from abc import ABC, abstractmethod
import tempfile
import aiofiles
import openai
from jugalbandi.core.errors import InternalServerException, ServiceUnavailableException
from llama_index import VectorStoreIndex, SimpleDirectoryReader, ServiceContext
from llama_index.llms import AzureOpenAI
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.docstore.document import Document
from langchain.embeddings.openai import OpenAIEmbeddings
from langchain.vectorstores.faiss import FAISS
from jugalbandi.document_collection import (
    DocumentCollection,
    DocumentFormat,
)
import json


class Indexer(ABC):
    @abstractmethod
    async def index(self, document_collection: DocumentCollection):
        pass


class GPTIndexer(Indexer):
    async def index(self, document_collection: DocumentCollection):
        try:
            files = [document_collection.local_file_path(file)
                     async for file in document_collection.list_files()]
            documents = SimpleDirectoryReader(input_files=files).load_data()
            ### For Azure OpenAI
            # llm = AzureOpenAI(
            #     engine="ada-002",
            #     model="text-embedding-ada-002",
            #     azure_endpoint="https://openaiapk01.openai.azure.com/",
            #     api_key="606abea98ee24949af802350d0e80cf6",
            #     api_version="2023-07-01-preview",
            # )
            # service_context = ServiceContext.from_defaults(llm=llm)
            # index = VectorStoreIndex.from_documents(documents, service_context=service_context)
            # ###
            
            index = VectorStoreIndex.from_documents(documents)
            index_content = index.storage_context.to_dict()
            index_str = json.dumps(index_content)
            await document_collection.write_index_file("gpt-index", "index.json",
                                                       bytes(index_str, "utf-8"))
        except openai.error.RateLimitError as e:
            raise ServiceUnavailableException(
                f"OpenAI API request exceeded rate limit: {e}"
            )
        except (openai.error.APIError, openai.error.ServiceUnavailableError):
            raise ServiceUnavailableException(
                "Server is overloaded or unable to answer your request at the moment."
                " Please try again later"
            )
        except Exception as e:
            raise InternalServerException(e.__str__())


class LangchainIndexer(Indexer):
    def __init__(self):
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=4 * 1024, chunk_overlap=0, separators=["\n", ".", ""]
        )

    async def index(self, doc_collection: DocumentCollection):
        source_chunks = []
        counter = 0
        async for filename in doc_collection.list_files():
            print(filename)
            content = await doc_collection.read_file(filename, DocumentFormat.TEXT)
            public_text_url = await doc_collection.public_url(filename,
                                                              DocumentFormat.TEXT)
            content = content.decode('utf-8')
            content = content.replace("\\n", "\n")
            print(content)
            for chunk in self.splitter.split_text(content):
                new_metadata = {
                    "source": str(counter),
                    "document_name": filename,
                    "txt_file_url": public_text_url,
                }
                source_chunks.append(
                    Document(page_content=chunk, metadata=new_metadata)
                )
                counter += 1
        try:
            print("into embeddings")
            # search_index = FAISS.from_documents(source_chunks,
            #                                     OpenAIEmbeddings(client=""))
            search_index = FAISS.from_documents(source_chunks,
                                                OpenAIEmbeddings(client="",deployment="ada-002"))
            print("finished embeddings")
            print(search_index)
            await self._save_index_files(search_index, doc_collection)
        except openai.error.RateLimitError as e:
            raise ServiceUnavailableException(
                f"OpenAI API request exceeded rate limit: {e}"
            )
        except (openai.error.APIError, openai.error.ServiceUnavailableError):
            raise ServiceUnavailableException(
                "Server is overloaded or unable to answer your request at the moment."
                " Please try again later"
            )
        except Exception as e:
            raise InternalServerException(e.__str__())

    async def _save_index_files(
        self, search_index: FAISS, doc_collection: DocumentCollection
    ):
        with tempfile.TemporaryDirectory() as temp_dir:
            # save in temporary directory
            search_index.save_local(temp_dir)

            async with aiofiles.open(f"{temp_dir}/index.pkl", "rb") as f:
                content = await f.read()
                await doc_collection.write_index_file("langchain", "index.pkl",
                                                      content)

            async with aiofiles.open(f"{temp_dir}/index.faiss", "rb") as f:
                content = await f.read()
                await doc_collection.write_index_file("langchain", "index.faiss",
                                                      content)
