from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, DateTime, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker
import datetime
from config import DATABASE_URL

Base = declarative_base()

class Worker(Base):
    """Модель для хранения информации о воркерах"""
    __tablename__ = 'workers'
    
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False, unique=True)
    server_address = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    # Отношение один-ко-многим с аккаунтами
    accounts = relationship("Account", back_populates="worker")
    
    def __repr__(self):
        return f"<Worker(id={self.id}, name={self.name}, active={self.is_active})>"


class Account(Base):
    """Модель для хранения информации о Telethon аккаунтах"""
    __tablename__ = 'accounts'
    
    id = Column(Integer, primary_key=True)
    phone = Column(String, nullable=False, unique=True)
    api_id = Column(String, nullable=False)
    api_hash = Column(String, nullable=False)
    session_string = Column(String)
    is_active = Column(Boolean, default=True)
    worker_id = Column(Integer, ForeignKey('workers.id'))
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    # Отношение многие-к-одному с воркером
    worker = relationship("Worker", back_populates="accounts")
    
    def __repr__(self):
        return f"<Account(id={self.id}, phone={self.phone}, active={self.is_active})>"


# Создание движка и сессии SQLAlchemy
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Функция для создания всех таблиц в базе данных
def create_tables():
    Base.metadata.create_all(bind=engine) 