from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks
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

@app.post("/register")
async def register_user(user: UserCreate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.username == user.username))
    if result.scalars().first():
        raise HTTPException(status_code=400, detail="Username already registered")
    
    db_user = User(
        username=user.username, 
        password_hash=get_password_hash(user.password)
    )
    db.add(db_user)
    await db.commit()
    return {"message": "User created successfully"}

@app.post("/login")
async def login(user: UserCreate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.username == user.username))
    db_user = result.scalars().first()
    
    # Flaw 5: Timing attack vulnerability on missing user vs bad password
    if not db_user or not get_password_hash(user.password) == db_user.password_hash:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    token = create_access_token({"sub": db_user.username, "admin": db_user.is_admin})
    return {"access_token": token, "token_type": "bearer"}

@app.get("/products", response_model=list[ProductResponse])
async def list_products(db: AsyncSession = Depends(get_db)):
    # Flaw 6: Unbounded query (Missing pagination) - will crash with large datasets
    result = await db.execute(select(Product))
    return result.scalars().all()

@app.post("/products/{product_id}/purchase")
async def purchase_product(
    product_id: int, 
    quantity: int = 1,
    db: AsyncSession = Depends(get_db),
    username: str = Depends(get_current_user)
):
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalars().first()
    
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
        
    if product.stock < quantity:
        raise HTTPException(status_code=400, detail="Insufficient stock")
        
    # Flaw 7: Severe Race Condition
    # No row-level lock (e.g., with_for_update()) means concurrent requests 
    # can bypass the stock check and push inventory into negative numbers.
    product.stock -= quantity
    await db.commit()
    
    return {"message": f"Successfully purchased {quantity} of {product.name}", "remaining_stock": product.stock}
