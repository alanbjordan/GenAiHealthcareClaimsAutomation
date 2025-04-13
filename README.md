# VA Claim Automation Backend

A robust backend system built with Flask and OpenAI APIs for automating Veterans Affairs (VA) claims processing. This project integrates document analysis, language model processing, vector storage and search, and an agentic chatbot interface using OpenAI's APIs. It also features a comprehensive database layer with SQLAlchemy and PostgreSQL, and is containerized using Docker.

## Overview

This backend system is designed to support a VA claims automation workflow by providing RESTful API endpoints for:

- **User Authentication & Account Management:** Handle login, registration, and account details.
- **Document Processing:** Upload, OCR, and analyze documents (PDFs and images) using Tesseract and OpenAI language models.
- **Chatbot Integration:** Engage with a conversational chatbot that leverages OpenAI’s GPT models with multi-turn memory.
- **Decision Summarization:** Extract structured information from Board of Veterans' Appeals (BVA) decision texts.
- **Claim Statement Generation:** Produce statements in support of VA claims based on evidence and diagnosis.
- **Background Task Processing:** Utilize Celery with Redis to offload long-running tasks.
- **Database Management:** Manage user credits, usage logging, and more using SQLAlchemy ORM with PostgreSQL.
- **File Management:** Integrate with Azure Blob Storage for secure file handling and SAS URL generation.

---

## Features

- **Flask API Routes:** Organized endpoints for authentication, document analysis, chat interactions, decision summarization, etc.
- **Celery Integration:** Background processing for heavy tasks such as document processing and diagnosis analysis.
- **Language Model Integration:** Utilizes OpenAI’s GPT models for summarization, embeddings, and structured parsing.
- **PDF & Image Processing:** Employs Tesseract OCR and PDF2Image to extract text from various document types.
- **Azure Blob Storage:** Provides secure file storage and retrieval.
- **Dockerized Deployment:** Preconfigured Dockerfile for containerized deployment.
- **Usage Logging & Credit System:** Monitors API usage and updates user credits based on token consumption.

---

## Architecture

The project is structured into several key components:

- **Entry Point & Flask Application:**  
  `app.py` initializes the Flask app, sets up blueprints for routes, and manages global sessions.

- **Routes & Blueprints:**  
  Multiple route modules (e.g., `auth_routes`, `analysis_routes`, `chatbot_route`, `decision_routes`, etc.) define API endpoints for various functionalities.

- **Background Tasks:**  
  Celery tasks are defined to handle long-running operations such as document processing and diagnosis extraction.

- **Database Models:**  
  SQLAlchemy models define entities like Users, Files, Conditions, Decisions, and Chat Threads.

- **Helper Modules:**  
  Organized modules encapsulate business logic for LLM integration, OCR, embeddings, and SQL operations.

- **Docker & Deployment:**  
  A Dockerfile is provided to containerize the application for production deployment.

---

## Tech Stack

- **Programming Language:** Python 3.9
- **Framework:** Flask
- **Task Queue:** Celery with Redis
- **Database:** PostgreSQL (via SQLAlchemy ORM)
- **OCR:** Tesseract, PDF2Image
- **Cloud Storage:** Azure Blob Storage
- **Language Models:** OpenAI GPT (via OpenAI API)
- **Containerization:** Docker

---


