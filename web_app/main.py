from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
import uvicorn
from contextlib import asynccontextmanager
from .services.data_loader import OrcamentoService

service = OrcamentoService()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Load data on startup
    print("Initializing Data Service...")
    service.load_and_calculate()
    yield
    # Clean up

app = FastAPI(lifespan=lifespan)

templates = Jinja2Templates(directory="web_app/templates")

# If we had static files
# app.mount("/static", StaticFiles(directory="web_app/static"), name="static")

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/api/grid")
async def get_grid_data():
    data = service.get_grid_data()
    return JSONResponse(content=data)

@app.get("/api/eap")
async def get_eap_data():
    # Return simplified list for EAP tree
    items = service.get_grid_data()
    # Filter only headers or meaningful items?
    # Or return full list and let frontend build tree
    return JSONResponse(content=items)

@app.get("/api/composition/{code}")
async def get_composition_json(code: str):
    data = service.get_composition(code)
    return JSONResponse(content=data)

@app.get("/api/item/{code}", response_class=HTMLResponse)
async def get_item_details(request: Request, code: str):
    # Return HTML snippet for Inspector
    # Find item in PO items
    item = next((i for i in service.po_items if i['code'] == code), None)
    
    if not item:
        return "<div>Item não encontrado</div>"

    comp_data = service.get_composition(code)
    
    return templates.TemplateResponse("inspector.html", {
        "request": request, 
        "item": item, 
        "composition": comp_data
    })

if __name__ == "__main__":
    uvicorn.run("web_app.main:app", host="127.0.0.1", port=8000, reload=True)
