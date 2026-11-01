import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import List

from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, Column, Integer, String, DateTime
from sqlalchemy.orm import sessionmaker, declarative_base, Session


DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://orders_user:orders_pass@postgres:5432/orders_db",
)

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()


# SQLAlchemy model
class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    customer_name = Column(String, nullable=False)
    product = Column(String, nullable=False)
    quantity = Column(Integer, nullable=False)
    status = Column(String, nullable=False, default="pending")
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))



class OrderCreate(BaseModel):
    customer_name: str = Field(min_length=1)
    product: str = Field(min_length=1)
    quantity: int = Field(gt=0)


class OrderResponse(BaseModel):
    id: int
    customer_name: str
    product: str
    quantity: int
    status: str
    created_at: str


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Converts a database row into the response shape.
def order_to_response(order: Order) -> OrderResponse:
    return OrderResponse(
        id=order.id,
        customer_name=order.customer_name,
        product=order.product,
        quantity=order.quantity,
        status=order.status,
        created_at=order.created_at.isoformat(),
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    
    Base.metadata.create_all(bind=engine)
    yield
    


app = FastAPI(title="OrderSys", lifespan=lifespan)


@app.get("/orders", response_model=List[OrderResponse])
def get_orders(db: Session = Depends(get_db)):
    orders = db.query(Order).all()
    return [order_to_response(o) for o in orders]


# No cache on purpose
@app.get("/orders/{order_id}", response_model=OrderResponse)
def get_order(order_id: int, db: Session = Depends(get_db)):
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order_to_response(order)


@app.post("/orders", status_code=201, response_model=OrderResponse)
def create_order(order_input: OrderCreate, db: Session = Depends(get_db)):
    order = Order(
        customer_name=order_input.customer_name,
        product=order_input.product,
        quantity=order_input.quantity,
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    return order_to_response(order)


@app.get("/health")
def health():
    return {"status": "ok"}