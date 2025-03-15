from sqlalchemy import create_engine, Column, Integer, String, Text, Boolean, DateTime, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
import datetime
from config import DATABASE_URL

# Создаем подключение к базе данных
engine = create_engine(DATABASE_URL)
Base = declarative_base()
Session = sessionmaker(bind=engine)


# Модель новости
class News(Base):
    __tablename__ = 'news'

    id = Column(Integer, primary_key=True)
    source_channel = Column(String(100), nullable=False)  # Канал-источник
    message_id = Column(Integer, nullable=False)  # ID сообщения в исходном канале
    date = Column(DateTime, default=datetime.datetime.now)
    content = Column(Text, nullable=False)  # Содержание новости
    has_media = Column(Boolean, default=False)  # Есть ли медиа в новости
    media_type = Column(String(20), nullable=True)  # Тип медиа (photo, video, etc.)
    media_path = Column(String(255), nullable=True)  # Путь к сохраненному медиафайлу
    is_reviewed = Column(Boolean, default=False)  # Просмотрено ли модератором
    is_approved = Column(Boolean, default=False)  # Одобрено ли модератором
    is_published = Column(Boolean, default=False)  # Опубликовано ли в целевой канал
    published_message_id = Column(Integer, nullable=True)  # ID опубликованного сообщения

    def __repr__(self):
        return f"<News(id={self.id}, source={self.source_channel}, reviewed={self.is_reviewed}, approved={self.is_approved})>"


# Создаем таблицы в базе данных, если их нет
def init_db():
    Base.metadata.create_all(engine)


# Функция для получения сессии базы данных
def get_session():
    return Session() 