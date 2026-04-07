\# Odoo Middleware



A REST API middleware that connects external apps to Odoo via XML-RPC.



\## Setup



1\. Clone the repo

2\. Install dependencies:

&#x20;  pip install -r requirements.txt

3\. Copy .env.example to .env and fill in your credentials:

&#x20;  copy .env.example .env

4\. Run the app:

&#x20;  py app.py



\## Endpoints



| Method | Endpoint | Description |

|--------|----------|-------------|

| GET | /health | Check if API is running |

| GET | /customers | Get all customers |

| POST | /customers | Create a customer |





\## Authentication

All endpoints (except /health) require an X-API-Key header.

