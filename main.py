from fastapi import FastAPI, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from database import engine, Base, get_db
from models import User, Product, UserCreate, ProductCreate, ProductResponse
from auth import get_password_hash, create_access_token, get_current_user

app = FastAPI(title="Inventory Microservice")

@app.on_event("startup")
async def startup_event():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

# --- ARCHITECTURAL UPGRADE: The Service Layer ---
# This decouples business and database logic from the API routing layer
class ProductService:
    def __init__(self, db: AsyncSession):
        self.db = db
        
    async def get_products(self, limit: int, offset: int):
        stmt = select(Product).offset(offset).limit(limit)
        result = await self.db.execute(stmt)
        return result.scalars().all()
        
    async def purchase(self, product_id: int, quantity: int):
        stmt = select(Product).where(Product.id == product_id).with_for_update()
        result = await self.db.execute(stmt)
        product = result.scalars().first()
        
        if not product:
            raise ValueError("Product not found")
        if product.stock < quantity:
            raise ValueError("Insufficient stock")
            
        product.stock -= quantity
        await self.db.commit()
        return product

# Dependency injection for the service
def get_product_service(db: AsyncSession = Depends(get_db)) -> ProductService:
    return ProductService(db)

# --- CLEAN ROUTING LAYER ---
@app.post("/register")
async def register_user(user: UserCreate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.username == user.username))
    if result.scalars().first():
        raise HTTPException(status_code=400, detail="Username already registered")
    
    db_user = User(username=user.username, password_hash=get_password_hash(user.password))
    db.add(db_user)
    await db.commit()
    return {"message": "User created successfully"}

@app.post("/login")
async def login(user: UserCreate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.username == user.username))
    db_user = result.scalars().first()
    
    if not db_user or not get_password_hash(user.password) == db_user.password_hash:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    token = create_access_token({"sub": db_user.username, "admin": db_user.is_admin})
    return {"access_token": token, "token_type": "bearer"}

@app.get("/products", response_model=list[ProductResponse])
async def list_products(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    service: ProductService = Depends(get_product_service)
):
    # Route is now extremely clean, only handling I/O
    return await service.get_products(limit, offset)

@app.post("/products/{product_id}/purchase")
async def purchase_product(
    product_id: int, 
    quantity: int = 1,
    service: ProductService = Depends(get_product_service),
    username: str = Depends(get_current_user)
):
    try:
        product = await service.purchase(product_id, quantity)
        return {"message": f"Successfully purchased {quantity} units", "remaining_stock": product.stock}
    except ValueError as e:
        # Translating service-level errors to HTTP errors
        raise HTTPException(status_code=400, detail=str(e))
