from enum import Enum
import operator
from typing import Dict, List, Optional
from datetime import date
from pydantic import BaseModel
from jugalbandi.library import DocumentMetaData, Library, DocumentSection
from jugalbandi.storage import Storage
from cachetools import TTLCache
from jugalbandi.core import aiocachedmethod
from jugalbandi.core.errors import (
    IncorrectInputException,
    InternalServerException,
)
from jugalbandi.jiva_repository import JivaRepository
from sklearn.feature_extraction.text import TfidfVectorizer
from langchain.vectorstores.faiss import FAISS
from langchain.embeddings.openai import OpenAIEmbeddings
from langchain.embeddings.azure_openai import AzureOpenAIEmbeddings
from langchain.docstore.document import Document
import re
import os
import openai
import json
import roman
import numpy as np
import tiktoken


class InvalidActMetaData(Exception):
    pass


class LegalDocumentType(Enum):
    ACT = "act"
    AMENDMENT = "amendment"
    RULES = "rules"
    REGULATION = "regulation"
    OTHER = "other"


class LegalKeys(str, Enum):
    LEGAL_DOC_TYPE = "legal_doc_type"
    LEGAL_ACT_NO = "legal_act_no"
    LEGAL_ACT_YEAR = "legal_act_year"
    LEGAL_ACT_JURISDICTION = "legal_act_jurisdiction"
    LEGAL_ACT_TITLE = "legal_act_title"
    LEGAL_MINISTRY = "legal_ministry"
    LEGAL_LAST_AMENDMENT_DATE = "legal_last_amendment_date"
    LEGAL_PASS_DATE = "legal_pass_date"
    LEGAL_EFFECTIVE_DATE = "legal_effective_date"


class Jurisdiction(str, Enum):
    CENTER = "center"
    KARNATAKA = "karnataka"


class ActMetaData(BaseModel):
    id: str
    no: str
    year: str
    title: str
    description: Optional[str] = None
    passing_date: date
    effective_from_date: date
    jurisdiction: Jurisdiction
    documents: List[DocumentMetaData] = []

    def add_document(self, doc_metadata: DocumentMetaData):
        self.documents.append(doc_metadata)

    @classmethod
    def get_act_id(cls, doc_metadata: DocumentMetaData) -> Optional[str]:
        jurisdiction = doc_metadata.get_extra_data(
            LegalKeys.LEGAL_ACT_JURISDICTION.value)
        act_no = doc_metadata.get_extra_data(LegalKeys.LEGAL_ACT_NO.value)
        act_year = doc_metadata.get_extra_data(LegalKeys.LEGAL_ACT_YEAR.value)
        if act_no is None or jurisdiction is None or act_year is None:
            return None

        return f"{jurisdiction}-{act_no}-{act_year}"

    @classmethod
    def from_document_metadata(cls, doc_metadata: DocumentMetaData) -> "ActMetaData":
        id = cls.get_act_id(doc_metadata)
        act_no = doc_metadata.get_extra_data(LegalKeys.LEGAL_ACT_NO.value)
        act_year = doc_metadata.get_extra_data(LegalKeys.LEGAL_ACT_YEAR.value)
        jurisdiction_value = doc_metadata.get_extra_data(
            LegalKeys.LEGAL_ACT_JURISDICTION
        )

        if act_no is None or jurisdiction_value is None:
            raise InvalidActMetaData(
                "act_no / jurisdiction missing in document metadata for "
                f"document {doc_metadata.id}"
            )

        title = doc_metadata.get_extra_data(LegalKeys.LEGAL_ACT_TITLE.value) or ""

        id = f"{jurisdiction_value}-{act_no}-{act_year}"

        return ActMetaData(
            id=id,
            no=act_no,
            year=act_year,
            title=title,
            passing_date=date.today(),
            effective_from_date=date.today(),
            jurisdiction=Jurisdiction(jurisdiction_value),
            documents=[],
        )


class LegalLibrary(Library):
    def __init__(self, id: str, store: Storage):
        super(LegalLibrary, self).__init__(id, store)
        self._act_cache: TTLCache = TTLCache(2, 900)
        self.jiva_repository = JivaRepository()

    @aiocachedmethod(operator.attrgetter("_act_cache"))
    async def act_catalog(self) -> Dict[str, ActMetaData]:
        catalog = await self.catalog()
        act_catalog: Dict[str, ActMetaData] = {}

        for _, doc_md in catalog.items():
            act_id = ActMetaData.get_act_id(doc_md)

            if act_id is not None:
                if act_id in act_catalog:
                    act_md = act_catalog[act_id]
                    act_md.add_document(doc_md)
                else:
                    act_md = ActMetaData.from_document_metadata(doc_md)
                    act_md.add_document(doc_md)
                    act_catalog[act_id] = act_md

        return act_catalog

    async def _abbreviate_query(self, query: str):
        openai.api_key = os.environ["OPENAI_API_KEY"]
        system_rules = (
                    "You are a helpful assistant who helps with expanding "
                    "the abbreviations present in the given sentence. "
                    "Do not change anything else in the given sentence."
                )
        result = openai.ChatCompletion.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": system_rules},
                    {"role": "user", "content": query},
                ],
            )
        return result["choices"][0]["message"]["content"]

    async def _preprocess_query(self, query: str) -> str:
        query = await self._abbreviate_query(query)
        words = ["Give me", "Give", "Find me", "Find", "Get me", "Get",
                 "Tell me", "Tell"]
        for word in words:
            pattern = re.compile(re.escape(word), re.IGNORECASE)
            query = pattern.sub("", query)

        return query.strip()

    async def _preprocess_section_number(self, section_number: str) -> str:
        try:
            result = int(section_number)
        except ValueError:
            try:
                result = roman.fromRoman(section_number)
            except Exception:
                raise IncorrectInputException("Incorrect section number format")
        return str(result)

    async def _get_document_section(self, section_number: str,
                                    document_id: str, document_metadata:
                                    DocumentMetaData) -> DocumentSection:
        document = self.get_document(document_id)
        byte_sections = await document.read_sections()
        sections = json.loads(byte_sections.decode('utf-8'))
        for section in sections:
            if section["Section number"] == section_number:
                return DocumentSection(section_id=section["Full section name"],
                                       section_name=section["Section name"],
                                       start_page=section["Start page"],
                                       metadata=document_metadata)

    async def _generate_response(self, docs: List[Document], query: str,
                                 email_id: str, past_conversations_history: bool):
        contexts = [document.page_content for document in docs]
        augmented_query = (
            "Information to search for answers:\n\n"
            "\n\n-----\n\n".join(context for context in contexts) +
            "\n\n-----\n\nQuery: " + query
        )
        system_rules = (
            "You are a helpful assistant who helps with answering questions "
            "based on the provided text. Extract and return the answer from the "
            "provided text and do not paraphrase the answer. "
            "If the answer cannot be found in the provided text, "
            "you admit that you do not know."
        )
        messages = [{"role": "system", "content": system_rules}]

        if past_conversations_history:
            past_conversations = await self.jiva_repository.get_conversation_logs(
                email_id=email_id)
            for convo in past_conversations:
                messages.append({"role": "user", "content": convo['query']})
                messages.append({"role": "assistant", "content": convo['response']})

        encoding = tiktoken.get_encoding('cl100k_base')
        num_tokens = len(encoding.encode(augmented_query))
        print(num_tokens)
        # if num_tokens > 3500:
        #     augmented_query = (
        #         "Information to search for answers:\n\n"
        #         "\n\n-----\n\n".join(contexts[i] for i in range(len(contexts)-1)) +
        #         "\n\n-----\n\nQuery: " + query
        #     )
        messages.append({"role": "user", "content": augmented_query})
        res = openai.ChatCompletion.create(
            model="gpt-4-1106-preview",
            messages=messages,
        )
        response = res["choices"][0]["message"]["content"]
        # await self.jiva_repository.insert_conversation_logs(email_id=email_id,
        #                                                     query=query,
        #                                                     response=response)
        return response

    async def search_titles(self, query: str) -> List[DocumentMetaData]:
        processed_query = await self._preprocess_query(query)
        processed_query = processed_query.strip()
        catalog = await self.catalog()
        titles_list = [catalog[cat].title for cat in catalog]

        vectorizer = TfidfVectorizer()
        tfidf_matrix = vectorizer.fit_transform(titles_list)
        title_vector = vectorizer.transform([processed_query])
        cosine_similarities = tfidf_matrix.dot(title_vector.T).toarray().flatten()
        top_3_indices = np.argsort(cosine_similarities)[-3:][::-1]

        result = []
        for i in top_3_indices:
            title = titles_list[i]
            for cat in catalog:
                if catalog[cat].title == title:
                    result.append(catalog[cat])

        return result

    async def search_sections(self, query: str):
        processed_query = await self._preprocess_query(query)
        processed_query = processed_query.strip()
        pattern = re.compile(r'\b[Ss]ec(?:tion)? (\d+|[IVXLCDM]+[A-Z]{0,3})',
                             re.IGNORECASE)
        matches = re.search(pattern, processed_query)
        if matches:
            section_number = matches.group(1)
            split_string = pattern.split(processed_query)
            split_string = list(filter(lambda x: x != "" and x != section_number,
                                       split_string))
            title = split_string[0].strip()
            title = re.sub(r'(?i)of', "", title)
            section_number = await self._preprocess_section_number(section_number)
            documents_metadata = await self.search_titles(title)
            document_metadata = documents_metadata[0]
            document_id = document_metadata.id
            document_sections = []
            document_sections.append(await self._get_document_section(
                                                                section_number,
                                                                document_id,
                                                                document_metadata))

            if document_sections[0] is None:
                raise InternalServerException("Cannot find section and page number")

            act_id = (document_metadata.extra_data["legal_act_jurisdiction"] + "-" +
                      document_metadata.extra_data["legal_act_no"] + "-" +
                      document_metadata.extra_data["legal_act_year"])

            act_catalog = await self.act_catalog()
            acts = act_catalog.values()
            for act in acts:
                if act.id == act_id:
                    relevant_act = act
                    break

            for act_document in relevant_act.documents:
                new_document_id = act_document.id
                if new_document_id != document_id:
                    new_document = self.get_document(new_document_id)
                    new_document_metadata = await new_document.read_metadata()
                    document_sections.append(await self._get_document_section(
                                                                section_number,
                                                                new_document_id,
                                                                new_document_metadata))

            return document_sections
        else:
            raise IncorrectInputException("Incorrect input query format")

    async def test_response(self, query: str):
        processed_query = await self._preprocess_query(query)
        processed_query = processed_query.strip()
        await self.download_index_files("index.faiss", "index.pkl")
        #vector_db = FAISS.load_local("indexes", OpenAIEmbeddings())
        vector_db = FAISS.load_local("indexes", AzureOpenAIEmbeddings(azure_deployment="ada-002",openai_api_version="2023-05-15",retry_min_seconds=30, disallowed_special=()))
        docs = vector_db.similarity_search(query=query, k=10)

        contexts = []
        unique_chunks = []
        for document in docs:
            file_name = document.metadata['file_name']
            contexts.append(document.page_content)
            if file_name not in unique_chunks:
                unique_chunks.append(file_name)

        if len(unique_chunks) >= 5:
            response = (
                "Please provide act name along with the query to search "
                "for answers"
            )
        else:
            augmented_query = (
                "Information to search for answers:\n\n"
                "\n\n-----\n\n".join(context for context in contexts) +
                "\n\n-----\n\nQuery: " + query
            )
            system_rules = (
                "You are a helpful assistant who helps with answering questions "
                "based on the provided text. Extract and return the answer from the "
                "provided text and do not paraphrase the answer. "
                "If the answer cannot be found in the provided text, "
                "you admit that you do not know."
            )
            messages = [{"role": "system", "content": system_rules}]

            encoding = tiktoken.get_encoding('cl100k_base')
            num_tokens = len(encoding.encode(augmented_query))
            print(num_tokens)
            messages.append({"role": "user", "content": augmented_query})
            res = openai.ChatCompletion.create(
                model="gpt-4-1106-preview",
                messages=messages,
            )
            response = res["choices"][0]["message"]["content"]

        await self.jiva_repository.insert_retriever_testing_logs(query=query,
                                                                 response=response)
        return response

    async def general_search(self, query: str, email_id: str):
        processed_query = await self._preprocess_query(query)
        processed_query = processed_query.strip()
        await self.download_index_files("index.faiss", "index.pkl")
        # vector_db = FAISS.load_local("indexes", OpenAIEmbeddings())
        vector_db = FAISS.load_local("indexes", AzureOpenAIEmbeddings(azure_deployment="ada-002",openai_api_version="2023-05-15",retry_min_seconds=30, disallowed_special=()))
        docs = vector_db.similarity_search(query=query, k=10)
        return await self._generate_response(docs=docs, query=processed_query,
                                             email_id=email_id,
                                             past_conversations_history=False)
