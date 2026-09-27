## architecture (single-region, India) , No frontDoor(CDN)
```
User (India)
    │
    │  GET video (SAS URL)
    ▼
┌────────────────────────────────────────────┐
│  Blob Storage  (South Central India)       │
│  <account>.blob.core.windows.net/videos    │
│                                            │
│  • SAS token (15 min) for auth             │
│  • Cache-Control: s-maxage=31536000        │
│  • Custom domain: video.mysite.com         │
└────────────────────────────────────────────┘

    │  (API calls only)
    ▼
┌────────────────────────────────────────────┐
│  FastAPI  (App Service / AKS, same region) │
│  • Auth, catalog, SAS generation           │
└────────────────────────────────────────────┘
```
| Signal | Action |
|--------|--------|
| Egress costs > ~$500/mo from Blob Storage | Add **Cloudflare** (free tier: 100 GB; Pro: $20/mo) in front |
| Need to serve users across multiple Indian metros with lower latency | Cloudflare or Bunny CDN (both have PoPs in India) |
| Need WAF / DDoS / Private Link | Then Front Door Standard makes sense |

#### Cloudflare setup (if you add it later)
- Create a Cloudflare zone for video.mysite.com
- Add an A/AAAA record → CNAME to <account>.blob.core.windows.net (use "CNAME flattening" or a proxy record)
- Enable Cache Everything for /videos/* paths
- Set Cache TTL: 1 year for video segments
- Point your API's SAS URL base to https://video.mysite.com instead of the raw blob URL
This gives you edge caching in India without the $35/mo Front Door base fee

#### TL;DR
For a single-region, early-stage video platform: skip the CDN entirely. Use Blob Storage + SAS tokens directly. Add Cloudflare (or similar) when egress costs or latency demand it. Front Door is the right choice only when you need its security features (WAF, Private Link, DDoS) or truly global distribution.
---
## Run the App
```
export AZURE_STORAGE_CONNECTION_STRING="DefaultEndpointsProtocol=https;AccountName=<name>;AccountKey=<key>;EndpointSuffix=core.windows.net"
export AZURE_STORAGE_ACCOUNT_URL="https://<name>.blob.core.windows.net"
export AZURE_BLOB_CONTAINER="videos"

uvicorn app:app --host 0.0.0.0 --port 8000
```
### Don't forget (one-time, on the storage account)
```
# CORS — without this the browser blocks <video> playback
az storage cors add \
  --account-name <your-account> \
  --services b \
  --methods GET HEAD OPTIONS \
  --origins "https://yourapp.com,http://localhost:8000" \
  --allowed-headers "Range,Accept-Ranges,Content-Range,Content-Type" \
  --exposed-headers "Accept-Ranges,Content-Range,Content-Length,Content-Type" \
  --max-age 3600
```
