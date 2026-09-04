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
    
    if not db_user or not get_password_hash(user.password) == db_user.password_hash:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    token = create_access_token({"sub": db_user.username, "admin": db_user.is_admin})
    return {"access_token": token, "token_type": "bearer"}

# --- IMPROVEMENT 1: Bounded Query with Pagination ---
@app.get("/products", response_model=list[ProductResponse])
async def list_products(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db)
):
    stmt = select(Product).offset(offset).limit(limit)
    result = await db.execute(stmt)
    return result.scalars().all()

# --- IMPROVEMENT 2: Atomic Row-Level Locking to Prevent Race Conditions ---
@app.post("/products/{product_id}/purchase")
async def purchase_product(
    product_id: int, 
    quantity: int = 1,
    db: AsyncSession = Depends(get_db),
    username: str = Depends(get_current_user)
):
    # with_for_update locks this specific product row until commit/rollback
    stmt = select(Product).where(Product.id == product_id).with_for_update()
    result = await db.execute(stmt)
    product = result.scalars().first()
    
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
        
    if product.stock < quantity:
        raise HTTPException(status_code=400, detail="Insufficient stock")
        
    product.stock -= quantity
    await db.commit()
    
    return {"message": f"Successfully purchased {quantity} of {product.name}", "remaining_stock": product.stock}
