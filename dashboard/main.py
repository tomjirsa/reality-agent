import uvicorn
from fastapi import FastAPI

from dashboard.routers import listings, market, configs

app = FastAPI(title="Reality Agent")
app.include_router(listings.router)
app.include_router(market.router)
app.include_router(configs.router)


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    uvicorn.run("dashboard.main:app", host="0.0.0.0", port=8080, log_level="info")
