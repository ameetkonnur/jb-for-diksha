# defining & setting environment variables
export random_number=$RANDOM
export rg_name=jugalbandi-$random_number
export preferred_region=eastus2
export azureopenai_region=eastus2
export azurespeech_region=eastus2
export azuretranslation_region=eastus2
export azurespeech_key=
export azuretranslation_key=
export azureopenai_account=azureopenai-$random_number
export azurespeech_account=azurespeech-$random_number
export azuretranslation_account=azuretranslation-$random_number
export subscription_id=
export container_image_fullpath=ameetk.azurecr.io/jugalbandi:7
export embeddings_model_name=ada-embeddings-$random_number
export gpt4_model_name=gpt4-$random_number
export storage_accout_name=jugalbandi$random_number
export storage_account_container_name=container$random_number
export container_app_name=jgapi-$random_number
export container_app_environment_name=jgenv-$random_number
export container_app_environment_workload_profile_name=jgenvwp-$random_number
export container_target_port=8080
export container_identity=

# get subscription id
subscription_id=$(az account show | jq -r .id)

# create resource group
az group create --name $rg_name --location $preferred_region

# create Speech, Translation & Azure OpenAI Resource
az cognitiveservices account create \
--name $azureopenai_account \
--resource-group $rg_name \
--location $azureopenai_region \
--kind OpenAI \
--sku S0 \
--custom-domain $azureopenai_account

# create Speech Resource
az cognitiveservices account create \
--name $azurespeech_account \
--resource-group $rg_name \
--location $azurespeech_region \
--kind SpeechServices \
--sku S0 \
--custom-domain $azurespeech_account

# create Translation Resource
az cognitiveservices account create \
--name $azuretranslation_account \
--resource-group $rg_name \
--location $azuretranslation_region \
--kind TextTranslation \
--sku S1 \
--custom-domain $azuretranslation_account


# get Speech, Translation & Azure OpenAI endpoint and keys
azureopenai_endpoint=$(az cognitiveservices account show \
--name $azureopenai_account \
--resource-group $rg_name \
| jq -r .properties.endpoint)

echo "Azure OpenAI Endpoint " + $azureopenai_endpoint

azureopenai_key=$(az cognitiveservices account keys list \
--name $azureopenai_account \
--resource-group $rg_name \
| jq -r .key1)

echo "Azure OpenAI Key " + $azureopenai_key

azuretranslation_key=$(az cognitiveservices account keys list \
--name $azuretranslation_account \
--resource-group $rg_name \
| jq -r .key1)

echo "Azure Translation Key " + $azuretranslation_key

azurespeech_key=$(az cognitiveservices account keys list \
--name $azurespeech_account \
--resource-group $rg_name \
| jq -r .key1)

echo "Azure Speech Key " + $azurespeech_key

# create text embeddings and GPT35 / GPT-4 deployments
az cognitiveservices account deployment create \
--name $azureopenai_account \
--resource-group  $rg_name \
--deployment-name $embeddings_model_name \
--model-name text-embedding-ada-002 \
--model-version 2 \
--model-format OpenAI \
--sku-capacity 30 \
--sku-name "Standard"

az cognitiveservices account deployment create \
--name $azureopenai_account \
--resource-group  $rg_name \
--deployment-name $gpt4_model_name \
--model-name gpt-35-turbo \
--model-version 0613 \
--model-format OpenAI \
--sku-capacity 50 \
--sku-name "Standard"

# create ContainerApp Environment, Workload Profile and Container App
az containerapp env create \
-n $container_app_environment_name \
-g $rg_name \
--location $preferred_region \
--enable-workload-profiles

az containerapp env workload-profile add \
-g $rg_name \
-n $container_app_environment_name \
--workload-profile-name $container_app_environment_workload_profile_name \
--workload-profile-type D4 \
--min-nodes 1 \
--max-nodes 3

# setting Container App Environment Variables
export env_OPENAI_API_TYPE=azure
export env_OPENAI_API_BASE=$azureopenai_endpoint
export env_OPENAI_API_KEY=$azureopenai_key
export env_OPENAI_API_VERSION=2023-05-15
export env_OPENAI_EMBEDDINGS_DEPLOYMENT=$embeddings_model_name
export env_OPENAI_CHATCOMPLETION_DEPLOYMENT_GPT4=$gpt4_model_name
export env_AZURE_SPEECH_KEY=$azurespeech_key
export env_AZURE_SPEECH_REGION=$azurespeech_region
export env_AZURE_TRANSLATION_KEY=$azuretranslation_key
export env_AZURE_TRANSLATION_RESOURCE_LOCATION=$azuretranslation_region
export env_OPENAI_CHATCOMPLETION_DEPLOYMENT_GPT3_5=$gpt4_model_name
export env_GPT4_PROMPT="Answer Based on Provided Texts: When you receive a legal question, search the provided legal texts and documents using the RAG system. Base your answer solely on the information found in these texts.  Accuracy and Relevance: Ensure that your responses are accurate and relevant to the question asked. Your answers should reflect the content and context of the provided legal texts.  Admitting Lack of Information: If the information necessary to answer a question is not available in the provided texts, respond with \"I don\'t know.\" Do not attempt to infer, guess, or provide information outside the scope of the provided texts.  Citing Sources: When providing an answer, cite the specific text or document from the provided materials. This will help in validating the response and maintaining transparency. Always, end the answer with \"For more information, visit https://tele-law.in\"  Confidentiality and Professionalism: Maintain a professional tone in all responses. Ensure confidentiality and do not request or disclose personal information.  Limitations Reminder: Regularly remind the user that your capabilities are limited to the information available in the provided legal texts and that you are an AI model designed to assist with legal information, not provide legal advice.  Example Interaction:  User: \"What are the legal requirements for drafting a will in India?” GPT-4: \"According to the Indian Succession Act, 1925, for a will to be valid in India, it must be in writing, signed by the testator, and witnessed by at least two individuals. [Source: Indian Succession Act, 1925 from provided legal texts]. For more information, visit https://tele-law.in\" User: \"What\'s the legal precedent for patent infringement cases involving software in Germany?\" GPT-4: \"I don\'t know. You may check the Tele Law website for more information: https://tele-law.in\" User: \"What is the Capital of Vietnam?\" GPT-4: \"Sorry, this doesn\'t look like a legal question. I can only attempt to answer legal queries, specific to India. You may also visit https://tele-law.in for more information.\""
export env_GPT3_5_PROMPT="Answer Based on Provided Texts: When you receive a legal question, search the provided legal texts and documents using the RAG system. Base your answer solely on the information found in these texts.  Accuracy and Relevance: Ensure that your responses are accurate and relevant to the question asked. Your answers should reflect the content and context of the provided legal texts.  Admitting Lack of Information: If the information necessary to answer a question is not available in the provided texts, respond with \"I don\'t know.\" Do not attempt to infer, guess, or provide information outside the scope of the provided texts.  Citing Sources: When providing an answer, cite the specific text or document from the provided materials. This will help in validating the response and maintaining transparency. Always, end the answer with \"For more information, visit https://tele-law.in\"  Confidentiality and Professionalism: Maintain a professional tone in all responses. Ensure confidentiality and do not request or disclose personal information.  Limitations Reminder: Regularly remind the user that your capabilities are limited to the information available in the provided legal texts and that you are an AI model designed to assist with legal information, not provide legal advice.  Example Interaction:  User: \"What are the legal requirements for drafting a will in India?” GPT-4: \"According to the Indian Succession Act, 1925, for a will to be valid in India, it must be in writing, signed by the testator, and witnessed by at least two individuals. [Source: Indian Succession Act, 1925 from provided legal texts]. For more information, visit https://tele-law.in\" User: \"What\'s the legal precedent for patent infringement cases involving software in Germany?\" GPT-4: \"I don\'t know. You may check the Tele Law website for more information: https://tele-law.in\" User: \"What is the Capital of Vietnam?\" GPT-4: \"Sorry, this doesn\'t look like a legal question. I can only attempt to answer legal queries, specific to India. You may also visit https://tele-law.in for more information.\""
export env_AZURE_BLOB_ACCOUNT_URL=https://$storage_accout_name.blob.core.windows.net
export env_AZURE_BLOB_CONTAINER=$storage_account_container_name
export env_AZURE_BLOB_BASE_URL=
export env_DOCUMENT_LOCAL_STORAGE_PATH=local
export env_ALLOW_AUTH_ACCESS=true
export env_ALLOW_INVALID_API_KEY=true

# create Container App
container_app_fqdn=$(az containerapp create \
--name $container_app_name \
--resource-group $rg_name \
--image $container_image_fullpath \
--environment $container_app_environment_name \
--ingres external \
--target-port $container_target_port \
--registry-identity system \
--registry-server ameetk.azurecr.io \
--cpu 2 \
--memory 4Gi \
--min-replicas 2 \
--max-replicas 4 \
--scale-rule-name http-rule \
--scale-rule-http-concurrency 50 \
--env-vars "OPENAI_API_TYPE=$env_OPENAI_API_TYPE" "OPENAI_API_BASE=$env_OPENAI_API_BASE" "OPENAI_API_KEY=$env_OPENAI_API_KEY" "OPENAI_API_VERSION=$env_OPENAI_API_VERSION" "OPENAI_EMBEDDINGS_DEPLOYMENT=$env_OPENAI_EMBEDDINGS_DEPLOYMENT" "OPENAI_CHATCOMPLETION_DEPLOYMENT_GPT4=$env_OPENAI_CHATCOMPLETION_DEPLOYMENT_GPT4" "AZURE_SPEECH_KEY=$env_AZURE_SPEECH_KEY" "AZURE_SPEECH_REGION=$env_AZURE_SPEECH_REGION" "AZURE_TRANSLATION_KEY=$env_AZURE_TRANSLATION_KEY" "AZURE_TRANSLATION_RESOURCE_LOCATION=$env_AZURE_TRANSLATION_RESOURCE_LOCATION" "OPENAI_CHATCOMPLETION_DEPLOYMENT_GPT3_5=$env_OPENAI_CHATCOMPLETION_DEPLOYMENT_GPT3_5" "GPT4_PROMPT=$env_GPT4_PROMPT" "GPT3_5_PROMPT=$env_GPT3_5_PROMPT" "AZURE_BLOB_ACCOUNT_URL=$env_AZURE_BLOB_ACCOUNT_URL" "AZURE_BLOB_CONTAINER=$env_AZURE_BLOB_CONTAINER" "AZURE_BLOB_BASE_URL=$env_AZURE_BLOB_BASE_URL" "GOOGLE_APPLICATION_CREDENTIALS=" "GCP_BUCKET_NAME=" "GCP_BUCKET_FOLDER_NAME=" "DOCUMENT_LOCAL_STORAGE_PATH=$env_DOCUMENT_LOCAL_STORAGE_PATH" "QA_DATABASE_NAME=" "QA_DATABASE_USERNAME=" "QA_DATABASE_PASSWORD=" "QA_DATABASE_IP=" "QA_DATABASE_PORT=" "ALLOW_AUTH_ACCESS=$env_ALLOW_AUTH_ACCESS" "TOKEN_ALGORITHM=" "TOKEN_JWT_SECRET_KEY=" "TOKEN_JWT_SECRET_REFRESH_KEY=" "AUTH_DATABASE_IP=" "AUTH_DATABASE_PORT=" "AUTH_DATABASE_USERNAME=" "AUTH_DATABASE_PASSWORD=" "AUTH_DATABASE_NAME=" "TENANT_DATABASE_IP=" "TENANT_DATABASE_PORT=" "TENANT_DATABASE_USERNAME=" "TENANT_DATABASE_PASSWORD=" "TENANT_DATABASE_NAME=" "ALLOW_INVALID_API_KEY=$env_ALLOW_INVALID_API_KEY" "BHASHINI_USER_ID=" "BHASHINI_API_KEY=" "BHASHINI_PIPELINE_ID=" \
--query properties.configuration.ingress.fqdn)

echo "Container App FQDN " + $container_app_fqdn

# Assign Managed Identity to Container App
az containerapp identity assign --name $container_app_name  --resource-group $rg_name --system-assigned

# Get Managed Identity for Container App
container_identity=$(az containerapp identity show --name $container_app_name --resource-group $rg_name | jq -r .principalId)
echo "Container Identity " + $container_identity

# Create Storage Account and Container to store files uploaded
az storage account create \
--name $storage_accout_name \
--resource-group $rg_name \
--location $preferred_region \
--sku Standard_LRS \
--allow-blob-public-access true

az storage container create \
--name $storage_account_container_name \
--account-name $storage_accout_name \
--public-access blob

# Assign Blob Contributor Rights to Container App
az role assignment create \
--assignee $container_identity \
--role "Storage Blob Data Contributor" \
--scope "subscriptions/$subscription_id/resourceGroups/$rg_name"
