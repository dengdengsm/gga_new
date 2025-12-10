# Smart Mermaid: AI-Powered Text-to-Mermaid Chart Tool

Smart Mermaid is a web application that leverages artificial intelligence to intelligently convert your text descriptions into Mermaid format chart code and render them as visual diagrams in real-time. Whether it's flowcharts, sequence diagrams, Gantt charts, or state diagrams, simply input your text, and the AI will generate the corresponding chart for you.

## Try it Out

[https://smart-mermaid.aizhi.site](https://smart-mermaid.aizhi.site)

**Note:** This application is completely free with a built-in API Key for direct use. To prevent resource abuse, we have set a daily limit of 5 free generations per user. If you need more usage, please contact the author for free additional quota.

<img src="https://github.com/user-attachments/assets/ce261409-13ff-4f6a-b749-13112f3b3067" width="200px">

## Preview

![PixPin_2025-05-23_11-25-46](https://github.com/user-attachments/assets/7ad74f73-68f3-499f-bcb4-f2b3e67336e8)

*Image: Smart Mermaid interface and generated chart*

## Core Advantages

* **Simplify Chart Drawing**: Say goodbye to the tedious manual writing of Mermaid code; generate charts quickly through natural language descriptions.
* **Increase Efficiency**: Rapidly transform ideas into visual charts, saving you time on documentation and presentations.
* **Intelligent Assistance**: AI automatically analyzes text, understands intent, and selects the appropriate chart type (or you can specify it).
* **Flexible Configuration**: Supports custom AI service configurations to meet the needs of different users.
* **Professional Experience**: Provides professional-grade chart editing and viewing experience with multiple rendering modes.

## Main Features

### 🎯 Core Features

* **Flexible Text Input**:
    * Manually type or paste text directly into the editor.
    * Supports uploading files (.txt, .md, .docx format).
    * Supports a maximum input length of 20,000 characters.

* **Intelligent AI Conversion**:
    * Integrates advanced AI models to analyze text content.
    * Supports multiple AI model selection (DeepSeek V3, DeepSeek R1, etc.).
    * Supports automatic identification of the best chart type or user-specified type.
    * Accurately generates Mermaid-compliant chart code.
    * Real-time streaming generation showing AI thinking process.

* **Dual Rendering Modes**:
    * **Excalidraw Renderer**: Hand-drawn style editable charts with element dragging and style modification.
    * **Mermaid Renderer**: Precise standard charts with professional-grade zoom and view controls.
    * One-click switching between rendering modes for different use cases.

* **Professional Code Editor**:
    * Integrated CodeMirror editor with Mermaid syntax highlighting.
    * Adjustable editor height (Small, Medium, Large, Extra Large).
    * Real-time code validation and preview updates.

### 🔧 Advanced Features

* **Smart Interface Design**:
    * **Left Panel Collapsing**: One-click hide editing panel for larger chart preview space.
    * **Responsive Layout**: Perfect adaptation for desktop and mobile devices.
    * **Dark Mode Support**: Comfortable night-time usage experience.

* **Enhanced View Controls**:
    * **Zoom Function**: Shift + scroll wheel zoom to avoid browser conflicts.
    * **Pan Operations**: Mouse drag to move view, keyboard shortcuts support.
    * **View Reset**: One-click restore to default view state.
    * **Fullscreen Mode**: Maximize workspace for focused chart editing.

* **Powerful Export Features**:
    * **SVG Export**: High-quality vector graphics download.
    * **PNG Export**: Bitmap format suitable for documents and presentations.
    * **Code Copy**: One-click copy Mermaid code to clipboard.

* **Custom AI Configuration**:
    * Supports configuring your own AI service API (OpenAI, Azure OpenAI, other compatible services).
    * Allows customization of API URL, API Key, and model name.
    * Supports model switching to choose the most suitable AI model.
    * Enjoy unlimited usage after configuring your own AI service.

* **Access Permission Management**:
    * Built-in access password feature; verified users enjoy unlimited usage.
    * Supports multiple usage modes: Free Limited → Password Verified → Custom Configuration.

* **Usage Statistics**:
    * Real-time display of remaining usage counts.
    * Locally stores usage records, reset daily.

## Usage Permissions Explained

Smart Mermaid offers three usage modes:

### 📊 Free Mode
- **Limit**: 5 free generations per day
- **Suitable for**: Light users, occasional use
- **No Configuration Needed**: Ready to use out-of-the-box

### 🔑 Password Mode
- **Permissions**: Unlimited usage after entering the access password
- **Suitable for**: Authorized users
- **How to Obtain**: Contact the author to get the access password

### ⚙️ Custom Configuration Mode
- **Permissions**: Unlimited usage
- **Suitable for**: Users with their own AI service
- **Configuration**: Fill in your API configuration in the settings
- **Advantage**: Complete autonomy, no dependencies

## How to Use

### Basic Usage Flow

1. **Input Descriptive Text**:
    * Directly type or paste your chart description into the text area on the left.
    * Alternatively, click the upload button to select a local `.txt`, `.md`, or `.docx` file.

2. **Select Configuration Options**:
    * Choose your desired chart type from the dropdown menu (e.g., Flowchart, Sequence Diagram).
    * Select AI model (if you have unlimited access, you can switch models in the model selector).
    * You can also select "Auto Select," letting the AI determine the most suitable chart type based on the text content.

3. **Generate Chart**:
    * Click the "Generate Chart" button.
    * The AI will process your text with real-time generation display.
    * The generated Mermaid code and rendered chart will appear in the right-hand area.

4. **View & Edit**:
    * View or modify the Mermaid code in the code editor, and the chart will update in real-time.
    * Use view control buttons for zooming, panning, resetting, and other operations.
    * Switch rendering modes to experience different chart styles.

5. **Export and Share**:
    * Use export functions to download SVG or PNG format charts.
    * Copy Mermaid code for use on other platforms.

### Interface Operation Guide

#### Left Editing Panel
- **Text Input Area**: Supports manual input or file upload
- **Code Editor**: Real-time editing and preview of Mermaid code
- **Height Adjustment**: Four preset heights (Small, Medium, Large, Extra Large)
- **Panel Collapse**: Click hide button for larger preview space

#### Right Preview Panel
- **Rendering Mode Switch**: Toggle between Excalidraw and Mermaid
- **View Controls**: Zoom, pan, reset, fullscreen and other operations
- **Export Functions**: Download charts or copy code

#### Interaction Shortcuts
- **Shift + Scroll Wheel**: Chart zooming
- **Ctrl + +/-/0**: Zoom control and reset
- **Mouse Drag**: Pan view
- **Two-finger Touch**: Mobile zoom support

### Unlock Unlimited Usage

#### Method One: Use Access Password
1. Click the settings button in the top right corner.
2. Enter the password in the "Access Password" tab.
3. Upon successful verification, you will have unlimited usage.

#### Method Two: Configure Custom AI Service
1. Click the settings button in the top right corner.
2. Fill in your configuration in the "AI Configuration" tab:
   - **API URL**: Your AI service address (e.g., `https://api.openai.com/v1`)
   - **API Key**: Your API key
   - **Model Name**: The model to use (e.g., `gpt-3.5-turbo`, `gpt-4`)
3. Save the configuration to enjoy unlimited usage and switch between different models in the model selector.

#### Obtain Access
- **Contact Author**: Scan the QR code in the app or contact via GitHub Issues.
- **BYO AI Service**: Use your own OpenAI API Key or other compatible services.

## Tech Stack

* **Frontend Framework**: Next.js 15 (using App Router)
* **UI Component Library**: shadcn/ui + Radix UI
* **CSS Framework**: Tailwind CSS v4
* **Code Editor**: CodeMirror 6 (with Mermaid syntax highlighting)
* **Chart Rendering & Processing**:
    * Excalidraw (`@excalidraw/excalidraw`)
    * Mermaid (`mermaid`)
    * Mermaid to Excalidraw conversion (`@excalidraw/mermaid-to-excalidraw`)
* **File Parsing**: mammoth (for processing `.docx` files)
* **AI Service**: Compatible with OpenAI API mode
* **State Management**: React Hook + Local Storage
* **Theme Support**: next-themes (dark/light mode)

## Local Deployment Guide

### Prerequisites

* Node.js 18.x or higher
* npm or yarn package manager

### Installation Steps

1. **Clone the repository**:
    ```bash
    git clone https://github.com/yourusername/smart-mermaid.git
    cd smart-mermaid
    ```
    *(Please replace `yourusername` with the actual repository path)*

2. **Install project dependencies**:
    ```bash
    npm install
    # Or
    yarn install
    ```

3. **Configure Environment Variables**:
    Create a `.env.local` file in the project root directory and fill in the following configuration:
    ```plaintext
    # AI Service Configuration (Required)
    AI_API_URL=https://api.openai.com/v1
    AI_API_KEY=your-api-key-here
    AI_MODEL_NAME=gpt-3.5-turbo
    
    # Application Configuration
    NEXT_PUBLIC_MAX_CHARS=20000
    NEXT_PUBLIC_DAILY_USAGE_LIMIT=5
    
    # Access Password (Optional)
    ACCESS_PASSWORD=set-your-access-password
    ```

    **Environment Variables Explained**:
    * `AI_API_URL`: Base URL of the AI service API (without `/chat/completions`)
    * `AI_API_KEY`: Your AI service API key
    * `AI_MODEL_NAME`: Specifies the AI model name to use
    * `NEXT_PUBLIC_MAX_CHARS`: Maximum number of characters allowed for user input (default 20,000)
    * `NEXT_PUBLIC_DAILY_USAGE_LIMIT`: Daily free usage limit per user (default 5)
    * `ACCESS_PASSWORD`: Optional, if set, users can enter this password to gain unlimited usage

4. **Start the development server**:
    ```bash
    npm run dev
    # Or
    yarn dev
    ```

5. **Access the application**:
    Open `http://localhost:3000` in your browser to access the locally deployed application.

### Production Deployment

```bash
# Build production version
npm run build

# Start production server
npm run start
```

## Project Highlights

### 🎨 User Experience Optimization
- **Smooth Animations**: Fluid panel collapse and view switching animations
- **Responsive Design**: Perfect adaptation to various screen sizes
- **Intuitive Operations**: Clear icons and operation hints
- **Accessibility Support**: Good keyboard navigation and screen reader support

### 🚀 Performance Optimization
- **Dynamic Loading**: Excalidraw component dynamic import reduces initial load time
- **Debounce Processing**: Avoids frequent re-rendering, improves interaction fluidity
- **Smart Caching**: Local storage of user configurations and preference settings
- **Memory Management**: Timely cleanup of event listeners prevents memory leaks

### 🔧 Technical Highlights
- **Modular Design**: Component-based architecture, easy to maintain and extend
- **Type Safety**: Complete parameter validation and error handling
- **Event System**: Cross-component global event communication mechanism
- **Configuration Center**: Unified configuration management service

## Contributions & Feedback

If you encounter any issues or have feature suggestions, please feel free to raise them via GitHub Issues. We also welcome you to fork this project and submit Pull Requests to contribute!

If this project is helpful to you, please give us a ⭐️ Star!