import streamlit as st
from PIL import Image
import json
import pandas as pd
import re
import io
import time
from io import BytesIO, StringIO
import pdfplumber
# from pdf2image import convert_from_bytes
from azure.cognitiveservices.vision.computervision import ComputerVisionClient
from azure.cognitiveservices.vision.computervision.models import OperationStatusCodes
from msrest.authentication import CognitiveServicesCredentials
from openai import AzureOpenAI

# Load configuration
config_path = 'config.json'
with open(config_path, 'r') as config_file:
    config = json.load(config_file)

azure_api_key = config['azure_api_key']
azure_api_version = config['azure_api_version']
azure_endpoint = config['azure_endpoint']
deployment_name = config['deployment_name']
azure_cv_api_key = config['azure_cv_api_key']
azure_cv_endpoint = config['azure_cv_endpoint']

# Initialize Azure clients
client = AzureOpenAI(
    api_key=azure_api_key,  
    api_version=azure_api_version,
    azure_endpoint=azure_endpoint
)

cv_client = ComputerVisionClient(
    endpoint=azure_cv_endpoint,
    credentials=CognitiveServicesCredentials(azure_cv_api_key)
)



def extract_text_from_image(image_stream):
    try:
        read_response = cv_client.read_in_stream(image_stream, raw=True)
        operation_location = read_response.headers["Operation-Location"]
        operation_id = operation_location.split("/")[-1]
        
        # Wait for the operation to complete
        while True:
            read_result = cv_client.get_read_result(operation_id)
            if read_result.status not in ['notStarted', 'running']:
                break
            time.sleep(1)
        
        extracted_text = []
        if read_result.status == OperationStatusCodes.succeeded:
            for page in read_result.analyze_result.read_results:
                for line in page.lines:
                    extracted_text.append(line.text)
        
        prompt = "\n".join(extracted_text)
        return prompt
    except Exception as e:
        st.error(f"Error extracting text: {e}")
        return ""
    
# def extract_text_from_pdf(pdf_stream):
#     try:
#         images  = convert_from_bytes(pdf_stream.read())
#         all_text = ""
#         for i, image in enumerate(images):
#             st.image(image, caption=f'Page {i+1}')
#             img_byte_arr = BytesIO()
#             image.save(img_byte_arr, format='PNG')
#             img_byte_arr = img_byte_arr.getvalue()

#             extracted_text = extract_text_from_image(BytesIO(img_byte_arr))
#             all_text += extracted_text + "\n\n"
#         return all_text.strip()
#     except Exception as e:
#         st.error("Error processing pdf as images: {e} ")
#         return ""

def extract_text_from_pdf(pdf_stream):
    try:
        all_text = ""
        # Open the PDF using pdfplumber
        with pdfplumber.open(pdf_stream) as pdf:
            # Loop through all the pages
            for i, page in enumerate(pdf.pages):
                st.write(f'Extracting text from Page {i+1}')
                # Extract text from the current page
                page_text = page.extract_text()
                if page_text:
                    all_text += page_text + "\n\n"
        return all_text.strip()
    except Exception as e:
        st.error(f"Error processing PDF: {str(e)}")
        return ""

def generate_text(prompt):
    try:
        response = client.chat.completions.create(
            model=deployment_name,
            messages=[
                {"role": "system", "content": "You are a helpful assistant that formats text into structured data."},
                {"role": "user", "content": f"""Parse the following text and structure it into an Excel-compatible format. Use '|' as the delimiter for each column in the output. Be flexible with the number of columns, and adjust the structure as needed based on the content. Do not write anything else or break format. Here are examples of the expected format, which you should adapt as necessary:
                
                Example 1: 
                Text to parse:
                FOOD MENU
                Paucek and Lage Restaurant
                MAIN COURSE
                Cheeseburger
                $34
                Cheese sandwich
                $22
                Chicken burgers
                $23
                Spicy chicken
                $33
                Hot dog
                $24
                APPETIZERS
                Fruit Salad
                $13
                Cocktails
                $12
                Nuggets
                $14
                Sandwich
                $13
                French Fries
                $15
                BEVERAGES
                Milk Shake
                $3
                Iced Tea
                $2
                Orange Juice
                $4
                Lemon Tea
                $3
                Coffee
                $5
                123-456-7890
                123 Anywhere St ., Any City

                Expected output:
                Category|Item|Price
                MAIN COURSE|Cheeseburger|$34
                MAIN COURSE|Cheese sandwich|$22
                MAIN COURSE|Chicken burgers|$23
                MAIN COURSE|Spicy chicken|$33
                MAIN COURSE|Hot dog|$24
                APPETIZERS|Fruit Salad|$13
                APPETIZERS|Cocktails|$12
                APPETIZERS|Nuggets|$14
                APPETIZERS|Sandwich|$13
                APPETIZERS|French Fries|$15
                BEVERAGES|Milk Shake|$3
                BEVERAGES|Iced Tea|$2
                BEVERAGES|Orange Juice|$4
                BEVERAGES|Lemon Tea|$3
                BEVERAGES|Coffee|$5

                Example 2:
                Text to parse:
                ME
                Appetizer.
                Garlic Bread
                6.99
                NU
                Potato Wedges
                6.99
                Meat Ball
                6.99
                Onion Rings
                6.99
                French Fries
                6.99
                Ratatouille
                6.99
                Main Course.
                Chef's Specials.
                Grilled Fingerlings
                6.99
                Grilled potatoes with a Western flair served with sauce of choice.
                Asian Pear Salad
                6.99
                Crisp pears and pecans with tender frisée, and maple syrup with cheese.
                Roasted Acorn Squash
                6.99
                Spicy-sweet, soft wedges potatoes which makes a no-fuss holiday meal.
                Smothered Chicken
                6.99
                Grilled chicken breast topped with mushrooms, onions and Cheese.
                Dessert.
                Banana Split
                6.99
                Cheese Cake
                6.99
                Chocolate Ice Cream
                6.99
                Fruit Cake
                6.99
                Drinks.
                Coffee
                6.99
                Ice / Hot Tea
                6.99
                Thai Tea
                6.99
                Soda
                6.99

                Expected output:
                Category|Item|Description|Price
                Appetizer|Garlic Bread||6.99
                Appetizer|Potato Wedges||6.99
                Appetizer|Meat Ball||6.99
                Appetizer|Onion Rings||6.99
                Appetizer|French Fries||6.99
                Appetizer|Ratatouille||6.99
                Main Course|Grilled Fingerlings|Grilled potatoes with a Western flair served with sauce of choice.|6.99
                Main Course|Asian Pear Salad|Crisp pears and pecans with tender frisée, and maple syrup with cheese.|6.99
                Main Course|Roasted Acorn Squash|Spicy-sweet, soft wedges potatoes which makes a no-fuss holiday meal.|6.99
                Main Course|Smothered Chicken|Grilled chicken breast topped with mushrooms, onions and Cheese.|6.99
                Dessert|Banana Split||6.99
                Dessert|Cheese Cake||6.99
                Dessert|Chocolate Ice Cream||6.99
                Dessert|Fruit Cake||6.99
                Drinks|Coffee||6.99
                Drinks|Ice / Hot Tea||6.99
                Drinks|Thai Tea||6.99
                Drinks|Soda||6.99

                Now, parse the following text. \n\n{prompt}"""}
            ],
            max_tokens=4096,
            temperature=0.3
        )
        structured_text = response.choices[0].message.content.strip()
        return structured_text
    except Exception as e:
        st.error(f"Error generating structured text: {e}")
        return ""

# def generate_text(prompt):
#     try:
#         response = client.chat.completions.create(
#             model=deployment_name,
#             messages=[
#                 {"role": "system", "content": "You are a helpful assistant that formats text into structured data."},
#                 {"role": "user", "content": f"""Parse the following text and structure it into an Excel-compatible format. Use '|' as the delimiter for each column in the output. Don't write anything else or break format.\n\n{prompt}"""}
#             ],
#             max_tokens=2000,
#             temperature=0.3
#         )
#         structured_text = response.choices[0].message.content.strip()
#         return structured_text
#     except Exception as e:
#         st.error(f"Error generating structured text: {e}")
#         return ""

    
def structured_text_to_df(structured_text):
    try:

        lines = structured_text.strip().split('\n')
        data = [line.split('|') for line in lines]
        max_fields = max(len(fields) for fields in data)
        data_padded = [fields + [''] * (max_fields - len(fields)) for fields in data]
        df = pd.DataFrame(data_padded)
        df.columns = df.iloc[0]
        df = df.drop(0).reset_index(drop=True)
        return df


    

    except Exception as e:
        st.error("Error converting the structured text into a dataframe: {e}")
        return pd.DataFrame()



def create_excel(df):
    try:
    
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name='Restaurant_menu')
        output.seek(0)
        return output
    except Exception as e:
        st.error(f"Error creating Excel file: {e}")
        return None
    


# Streamlit app
st.title("Image Text Extraction")


if 'extracted_text' not in st.session_state:
    st.session_state.extracted_text = ""
if 'structured_text' not in st.session_state:
    st.session_state.structured_text = ""
if 'df' not in st.session_state:
    st.session_state.df = pd.DataFrame()

# File uploader
uploaded_file = st.file_uploader("Choose an image or PDF", type=["jpg", "png", "jpeg", "pdf"])

if uploaded_file is not None:
    if uploaded_file.type in ["image/jpeg", "image/png", "image/jpg"]:
        image = Image.open(uploaded_file)
        
        # Display the image
        st.image(image, caption='Uploaded Image', use_column_width=True)
        
        # Extract text from image using Azure Computer Vision
        st.write("Extracting text from the image...")
        image_stream = BytesIO(uploaded_file.getvalue())
        extracted_text = extract_text_from_image(image_stream)
    elif uploaded_file.type == "application/pdf":
        st.write("Processing PDF...")
        # extracted_text = extract_text_from_pdf(uploaded_file)
        extracted_text = extract_text_from_pdf(uploaded_file)
    
    # Display the extracted text
    if extracted_text:
        st.session_state.extracted_text = extracted_text
        

if st.session_state.extracted_text:
    # Generate structured text using Azure OpenAI
    st.write("Extracted Text:")
    st.text_area("Extracted Text Area", st.session_state.extracted_text, height=200)
    if st.button("Generate structured_text"):
        st.write("Generating structured text...")
        # print("Extracted_text",extracted_text)
        structured_text = generate_text(st.session_state.extracted_text)
        if structured_text:
            st.session_state.structured_text = structured_text
            st.text_area("Structured Text Area", st.session_state.structured_text, height=200)
            st.session_state.df = structured_text_to_df(structured_text)
            # print("Structured_text_to_df",st.session_state.df)
          
if not st.session_state.df.empty:
    st.write("Edit the table below and map the categories to items:")
    edited_df = st.data_editor(st.session_state.df , num_rows = "dynamic")
    st.session_state.df = edited_df

    # if st.button("Download Edited Table"):
    output = create_excel(edited_df)
    if output:
        st.write("Creating Excel file...")
        st.download_button(
                label="Download Excel file",
                data=output,
                file_name="restaurant_menu.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

            
                