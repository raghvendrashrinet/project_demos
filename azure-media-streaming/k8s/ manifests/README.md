```
k8s/
├── namespace.yaml
├── configmap.yaml
├── secret.yaml
├── deployment.yaml
├── service.yaml
└── ingress.yaml

```

### Build & Push to ACR
```
### # Create ACR (one-time)
az acr create -n myregistry -g my-rg --sku Basic

# Login
az acr login -n myregistry

# Build & push
docker build -t myregistry.azurecr.io/video-platform:latest .
docker push myregistry.azurecr.io/video-platform:latest
```

### Deploy to AKS
```
# Enable image pull from ACR (one-time)
az aks update -n my-aks -g my-rg --enable-acr-sku Basic --acr-name myregistry

# Apply manifests
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/secret.yaml
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml
kubectl apply -f k8s/ingress.yaml

# Verify
kubectl get pods -n video-platform
kubectl logs -n video-platform -l app=video-api   
```

### (Optional) Use Managed Identity instead of connection string
If you want to eliminate the secret entirely (best practice):

```
# deployment.yaml — add to pod spec:
spec:
  containers:
    - name: api
      env:
        - name: AZURE_CLIENT_ID
          valueFrom:
            secretKeyRef:
              name: video-mi
              key: client-id
```
And assign the Key Vault Secrets User + Storage Blob Data Contributor roles to the pod identity on the Key Vault / Storage Account. Then remove AZURE_STORAGE_CONNECTION_STRING from the secret — DefaultAzureCredential() picks up the pod identity automatically.

### Final topology
```
Ingress (nginx)
    │
    ▼
Service (ClusterIP:80)
    │
    ▼
Deployment (2 replicas, video-api)
    │
    ├─► Blob Storage (direct, SAS URLs to browser)
    └─► (future) Cosmos DB / SQL for metadata
```
No CDN, no Front Door — the Ingress just routes API calls; video bytes go straight from Blob Storage to the browser.















