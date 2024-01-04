export rg_name=
export preferred_region=
export azureopenai_region=
export azureopenai_account=
export subscription=
export container_image_fullpath=
export embeddings_model_name=
export gpt4_model_name=
export storage_accout_name=
export storage_account_container_name=
export container_app_name=
export container_app_environment_name=
export container_target_port=
export env_settings=
export container_identity=

# create resource group
az group create $rg_name $preferred_region

# create Azure OpenAI Resource
az cognitiveservices account create \
--name $azureopenai_account \
--resource-group $rg_name \
--location $azureopenai_region \
--kind OpenAI \
--sku s0 \
--subscription $subscription

# get Azure OpenAI endpoint and keys
azureopenai_endpoint = az cognitiveservices account show \
--name $azureopenai_account \
--resource-group $rg_name \
| jq -r .properties.endpoint

echo "Azure OpenAI Endpoint " + $azureopenai_endpoint

azureopenai_key = az cognitiveservices account show \
--name $azureopenai_account \
--resource-group $rg_name \
| jq -r .key1

echo "Azure OpenAI Key " + $azureopenai_key

# create text embeddings and GPT-4 deployments
az cognitiveservices account deployment create \
--name $azureopenai_account \
--resource-group  $rg_name \
--deployment-name $embeddings_model_name \
--model-name text-embedding-ada-002 \
--model-version "1" \
--model-format OpenAI \
--sku-capacity "1" \
--sku-name "Standard"

az cognitiveservices account deployment create \
--name $azureopenai_account \
--resource-group  $rg_name \
--deployment-name $gpt4_model_name \
--model-name gpt4-turbo \
--model-version "1" \
--model-format OpenAI \
--sku-capacity "1" \
--sku-name "Standard"

# create ContainerApp
az containerapp create \
--name $container_app_name \
--resource-group $rg_name \
--environment $container_app_environment_name \
--image $container_image_fullpath \
--ingres external \
--target-port $container_target_port \
--cpu 2 \
--memory 4Gi \
--min-replicas 2 \
--max-replicas 4 \
--scale-rule-name http-rule \
--scale-rule-http-concurrency 50 \
--env-vars $env_settings \
--query properties.configuration.ingress.fqdn

# Assign Managed Identity to Container App
az containerapp identity assign --name $container_app_name  --resource-group $rg_name --system-assigned

# Get Managed Identity for Container App
container_identity = (az containerapp identity show --name $container_app_name --resource-group $rg_name)

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
--scope "subscriptions/$subscription/resourceGroups/$rg_name/providers/Microsoft.Storage/storageAccounts/$storage_account_name"
