import streamlit as st
import pandas as pd
import sqlite3
import os
import csv
from io import StringIO
import anthropic
import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
from dotenv import load_dotenv
import uuid

# Load environment variables
load_dotenv()

# Configure Anthropic API
client = anthropic.Anthropic(
    api_key=os.getenv("ANTHROPIC_API_KEY", "your-api-key")
)

# Language lists
# European Languages
european_languages = [
    "English", 
    "Albanian",
    "Bosnian",
    "Bulgarian",
    "Catalan",
    "Croatian", 
    "Czech", 
    "Danish", 
    "Dutch", 
    "Estonian", 
    "Finnish", 
    "French", 
    "German", 
    "Greek", 
    "Hungarian", 
    "Icelandic",
    "Irish",
    "Italian", 
    "Latvian", 
    "Lithuanian", 
    "Macedonian",
    "Maltese",
    "Norwegian", 
    "Polish", 
    "Portuguese", 
    "Romanian", 
    "Russian", 
    "Serbian",
    "Slovak", 
    "Slovenian", 
    "Spanish", 
    "Swedish", 
    "Turkish", 
    "Ukrainian"
]

# APAC Languages
apac_languages = [
    "Arabic",
    "Bengali",
    "Burmese",
    "Chinese (Simplified)", 
    "Chinese (Traditional)", 
    "Filipino/Tagalog",
    "Hindi", 
    "Indonesian", 
    "Japanese", 
    "Khmer",
    "Korean", 
    "Lao",
    "Malay", 
    "Mongolian",
    "Nepali",
    "Persian/Farsi",
    "Sinhalese",
    "Tamil",
    "Telugu",
    "Thai", 
    "Urdu",
    "Vietnamese"
]

# Combine all languages and sort alphabetically
all_languages = sorted(european_languages + apac_languages)

# Helper function to standardize language names
def standardize_language_name(language):
    """Convert display language names to standard format for the API."""
    # Handle special cases
    if language == "Chinese (Simplified)":
        return "Chinese (Simplified)"
    elif language == "Chinese (Traditional)":
        return "Chinese (Traditional)"
    elif language == "Filipino/Tagalog":
        return "Tagalog"
    elif language == "Persian/Farsi":
        return "Farsi"
    # Return the standard name for other languages
    return language

# Database setup
def setup_database():
    conn = sqlite3.connect('seo_keywords.db')
    cursor = conn.cursor()
    
    # Create tables if they don't exist
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS original_keywords (
        id TEXT PRIMARY KEY,
        keyword TEXT NOT NULL,
        category TEXT NOT NULL,
        search_intent TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS localized_keywords (
        id TEXT PRIMARY KEY,
        original_id TEXT,
        localized_keyword TEXT NOT NULL,
        language TEXT NOT NULL,
        back_translation TEXT,
        confidence_score REAL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (original_id) REFERENCES original_keywords (id)
    )
    ''')
    
    conn.commit()
    return conn

# Function to generate a keyword localization prompt
def create_localization_prompt(keyword, category, source_language, target_language):
    prompt = f"""
    I need to localize the following SEO keyword from {source_language} to {target_language}.
    
    Keyword: "{keyword}"
    Category: {category}
    
    Remember that localization is different from translation. I need the keyword that native {target_language} speakers would naturally use when searching for this concept.
    
    Please provide:
    1. The localized keyword in {target_language}
    2. A back-translation of this localized keyword to {source_language}
    3. A confidence score (1-10) for this localization
    4. A brief explanation of your choice
    
    Format your response as follows:
    LOCALIZED_KEYWORD: [localized keyword]
    BACK_TRANSLATION: [back translation]
    CONFIDENCE: [score]
    EXPLANATION: [brief explanation]
    """
    return prompt

# Function to localize a single keyword using Claude
async def localize_keyword(keyword, category, source_language, target_language):
    prompt = create_localization_prompt(
        keyword, 
        category, 
        standardize_language_name(source_language), 
        standardize_language_name(target_language)
    )
    
    try:
        response = client.messages.create(
            model="claude-3-7-sonnet-20250219",
            max_tokens=1000,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )
        
        result = response.content[0].text
        
        # Parse the response
        localized_keyword = None
        back_translation = None
        confidence = None
        explanation = None
        
        for line in result.split('\n'):
            if line.startswith('LOCALIZED_KEYWORD:'):
                localized_keyword = line.replace('LOCALIZED_KEYWORD:', '').strip()
            elif line.startswith('BACK_TRANSLATION:'):
                back_translation = line.replace('BACK_TRANSLATION:', '').strip()
            elif line.startswith('CONFIDENCE:'):
                confidence_text = line.replace('CONFIDENCE:', '').strip()
                try:
                    confidence = float(confidence_text)
                except ValueError:
                    confidence = 5.0  # Default if parsing fails
            elif line.startswith('EXPLANATION:'):
                explanation = line.replace('EXPLANATION:', '').strip()
        
        return {
            'original_keyword': keyword,
            'category': category,
            'localized_keyword': localized_keyword,
            'language': target_language,
            'back_translation': back_translation,
            'confidence': confidence,
            'explanation': explanation
        }
    except Exception as e:
        st.error(f"Error localizing keyword '{keyword}': {str(e)}")
        return {
            'original_keyword': keyword,
            'category': category,
            'localized_keyword': f"ERROR: {str(e)}",
            'language': target_language,
            'back_translation': '',
            'confidence': 0,
            'explanation': f"Localization failed with error: {str(e)}"
        }

# Function to process a batch of keywords
def process_keywords_batch(keywords_data, source_language, target_language, max_workers=5):
    results = []
    
    async def process_all():
        tasks = []
        for keyword_data in keywords_data:
            keyword = keyword_data.get('keyword', '')
            category = keyword_data.get('category', 'uncategorized')
            task = localize_keyword(keyword, category, source_language, target_language)
            tasks.append(task)
        
        # Process in batches to avoid rate limiting
        batch_size = 10
        all_results = []
        
        for i in range(0, len(tasks), batch_size):
            batch = tasks[i:i+batch_size]
            batch_results = await asyncio.gather(*batch)
            all_results.extend(batch_results)
            
            # Add a small delay between batches
            if i + batch_size < len(tasks):
                await asyncio.sleep(2)
        
        return all_results
    
    # Run async code in a synchronous context
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    results = loop.run_until_complete(process_all())
    loop.close()
    
    return results

# Save results to database
def save_to_database(conn, results):
    cursor = conn.cursor()
    
    for result in results:
        # Generate UUIDs for both records
        original_id = str(uuid.uuid4())
        localized_id = str(uuid.uuid4())
        
        # Insert original keyword
        cursor.execute(
            "INSERT OR IGNORE INTO original_keywords (id, keyword, category, search_intent) VALUES (?, ?, ?, ?)",
            (original_id, result['original_keyword'], result['category'], result.get('explanation', ''))
        )
        
        # Insert localized keyword
        cursor.execute(
            "INSERT INTO localized_keywords (id, original_id, localized_keyword, language, back_translation, confidence_score) VALUES (?, ?, ?, ?, ?, ?)",
            (localized_id, original_id, result['localized_keyword'], result['language'], result['back_translation'], result['confidence'])
        )
    
    conn.commit()

# Export results to CSV
def export_to_csv(results):
    df = pd.DataFrame(results)
    return df.to_csv(index=False)

# Function to parse uploaded CSV
def parse_csv(content):
    data = []
    
    # Check if content is a string (text) or binary
    if isinstance(content, bytes):
        content = content.decode('utf-8')
    
    csv_reader = csv.DictReader(StringIO(content))
    
    for row in csv_reader:
        if 'keyword' in row:
            data.append(row)
        else:
            st.error("CSV file must contain a 'keyword' column")
            return []
    
    return data

# Streamlit UI
def main():
    st.set_page_config(page_title="SEO Keyword Localizer", layout="wide")
    
    st.title("SEO Keyword Localizer")
    st.markdown("""
    This tool localizes SEO keywords to different languages, preserving search intent rather than just translating words.
    """)
    
    # Setup database connection
    conn = setup_database()
    
    # Sidebar for configuration
    st.sidebar.header("Language Configuration")
    
    language_filter = st.sidebar.radio(
        "Filter languages by region",
        ["All Languages", "European Languages", "APAC Languages"],
        index=0
    )
    
    if language_filter == "All Languages":
        language_list = all_languages
    elif language_filter == "European Languages":
        language_list = european_languages
    else:  # APAC Languages
        language_list = apac_languages
    
    source_language = st.sidebar.selectbox(
        "Source Language",
        language_list
    )
    
    # Filter out the source language from target options
    target_language_list = [lang for lang in language_list if lang != source_language]
    
    target_language = st.sidebar.selectbox(
        "Target Language",
        target_language_list
    )
    
    # File uploader for CSV
    st.subheader("Upload Keywords")
    uploaded_file = st.file_uploader("Upload a CSV file with keywords", type=["csv"])
    
    # Manual input option
    st.subheader("Or Enter Keywords Manually")
    
    manual_keywords = st.text_area(
        "Enter keywords (one per line)",
        height=150,
        help="Enter one keyword per line. Optionally use comma to specify category: keyword, category"
    )
    
    # Process data button
    start_processing = st.button("Start Localization")
    
    if start_processing:
        keywords_data = []
        
        if uploaded_file is not None:
            file_content = uploaded_file.read()
            keywords_data = parse_csv(file_content)
            
        elif manual_keywords:
            for line in manual_keywords.split('\n'):
                if line.strip():
                    parts = [part.strip() for part in line.split(',', 1)]
                    if len(parts) == 1:
                        keywords_data.append({'keyword': parts[0], 'category': 'uncategorized'})
                    else:
                        keywords_data.append({'keyword': parts[0], 'category': parts[1]})
        
        if keywords_data:
            # Show progress
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            status_text.text(f"Localizing {len(keywords_data)} keywords from {source_language} to {target_language}...")
            
            # Process keywords in batches
            results = process_keywords_batch(keywords_data, source_language, target_language)
            
            # Update progress
            progress_bar.progress(100)
            status_text.text(f"Localization complete! Processed {len(results)} keywords.")
            
            # Display results
            st.subheader("Localization Results")
            results_df = pd.DataFrame(results)
            st.dataframe(results_df)
            
            # Save to database
            save_to_database(conn, results)
            
            # Export options
            st.subheader("Export Results")
            csv_data = export_to_csv(results)
            st.download_button(
                label="Download CSV",
                data=csv_data,
                file_name=f"localized_keywords_{target_language}_{int(time.time())}.csv",
                mime="text/csv"
            )
        else:
            st.warning("Please upload a CSV file or enter keywords manually.")
    
    # Database explorer
    st.subheader("Database Explorer")
    if st.button("View All Localized Keywords"):
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                ok.keyword as original_keyword, 
                ok.category, 
                lk.localized_keyword, 
                lk.language, 
                lk.back_translation, 
                lk.confidence_score
            FROM 
                localized_keywords lk
            JOIN 
                original_keywords ok ON lk.original_id = ok.id
            ORDER BY 
                ok.category, ok.keyword
        """)
        
        results = cursor.fetchall()
        if results:
            df = pd.DataFrame(results, columns=["Original Keyword", "Category", "Localized Keyword", "Language", "Back Translation", "Confidence"])
            st.dataframe(df)
            
            # Export database
            st.download_button(
                label="Export Database to CSV",
                data=df.to_csv(index=False),
                file_name=f"keyword_database_export_{int(time.time())}.csv",
                mime="text/csv"
            )
        else:
            st.info("No localized keywords found in the database.")

if __name__ == "__main__":
    main()