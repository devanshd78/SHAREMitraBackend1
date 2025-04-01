<!-- # ShareMitra Flask Backend

This repository contains the backend for the ShareMitra application. It is built using Flask and provides endpoints for user authentication, task management, image analysis, and payment details submission with IFSC validation. Data is stored in MongoDB, and the project integrates with external services (Tesseract OCR and Razorpay IFSC API).

## Getting Started

### Prerequisites

- **Python 3.7+**
- **MongoDB:** Ensure you have a MongoDB instance running (default: `mongodb://localhost:27017`).
- **Tesseract OCR:**  
  On macOS, install via Homebrew:
  ```bash
  brew install tesseract -->




# ShareMitra Flask Backend

The ShareMitra Flask Backend is a robust and scalable backend service for the ShareMitra application. Built on Flask, it offers secure endpoints for user authentication, task management, image analysis, and payment processing with IFSC code validation. The backend utilizes MongoDB for data storage and integrates with external services such as Tesseract OCR and the Razorpay IFSC API to deliver advanced functionalities.

## Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
- [API Endpoints](#api-endpoints)
- [Integration Details](#integration-details)
- [Contributing](#contributing)
- [License](#license)

## Overview

The ShareMitra Flask Backend is engineered to provide a secure, efficient, and extendable server-side solution for the ShareMitra application. It is designed with modularity in mind, enabling easy expansion and integration with various external services for image processing and banking validations.

## Features

- **User Authentication:** Secure registration and login capabilities.
- **Task Management:** Create, read, update, and delete (CRUD) operations for user tasks.
- **Image Analysis:** Leverages Tesseract OCR to extract and analyze text from images.
- **Payment Processing:** Validates and processes payment details using the Razorpay IFSC API.
- **Data Persistence:** Stores application data in MongoDB for high performance and scalability.
- **External Integrations:** Seamlessly integrates with Tesseract OCR for image recognition and Razorpay for banking validations.

## Prerequisites

Ensure you have the following installed and configured on your development machine:

- **Python 3.7+**: Required to run the Flask application.
- **MongoDB**: A running MongoDB instance (default URI: `mongodb://localhost:27017`).
- **Tesseract OCR**: Essential for image analysis.
  - **macOS**: Install via Homebrew:
    ```bash
    brew install tesseract
    ```
  - **Other Platforms**: Refer to the [Tesseract documentation](https://github.com/tesseract-ocr/tesseract) for installation instructions.

## Installation

Follow these steps to set up the project locally:

1. **Clone the repository:**
   ```bash
   git clone https://github.com/ipriyanshu25/SHAREMitra.git
   cd SHAREMitra
