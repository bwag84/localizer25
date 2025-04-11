import sys
import streamlit as st
import pandas as pd
import sqlite3
import os
import csv
from io import StringIO
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from dotenv import load_dotenv
import uuid
import asyncio

# --- PAGE CONFIG MUST BE THE FIRST STREAMLIT COMMAND ---
st.set_page_config(page_title="Advanced SEO Keyword Localizer", layout="wide")
# -------------------------------------------------------

st.write(f"Streamlit is using Python executable: {sys.executable}")

# Load environment variables
load_dotenv()

# Configure API clients with error handling
llm_clients = {}

# Initialize Anthropic (Claude) client
try:
    import anthropic
    claude_api_key = os.getenv("ANTHROPIC_API_KEY")
    if claude_api_key:
        llm_clients["Claude"] = anthropic.Anthropic(api_key=claude_api_key)
except ImportError:
    st.warning("Anthropic package not installed. Claude models will not be available.")
except Exception as e:
    st.warning(f"Error initializing Claude client: {str(e)}")

# Initialize OpenAI client
try:
    import openai
    openai_api_key = os.getenv("OPENAI_API_KEY")
    if openai_api_key:
        # Use the correct initialization based on the OpenAI package version
        openai.api_key = openai_api_key
        llm_clients["OpenAI"] = openai
except ImportError:
    st.warning("OpenAI package not installed. OpenAI models will not be available.")
except Exception as e:
    st.warning(f"Error initializing OpenAI client: {str(e)}")

# Initialize Google Gemini client
try:
    import google.generativeai as genai
    google_api_key = os.getenv("GOOGLE_API_KEY")
    if google_api_key:
        genai.configure(api_key=google_api_key)
        llm_clients["Gemini"] = genai
except ImportError:
    st.warning("Google Generative AI package not installed. Gemini models will not be available.")
except Exception as e:
    st.warning(f"Error initializing Gemini client: {str(e)}")

# Initialize Mistral client - UPDATED to use new client API
# try:
#     from mistralai.client.client import MistralClient
#     from mistralai.models.chat_completion import ChatMessage
#     mistral_api_key = os.getenv("MISTRAL_API_KEY")
#     if mistral_api_key:
#         llm_clients["Mistral"] = MistralClient(api_key=mistral_api_key)
# except ImportError:
#     st.warning("Mistral AI package not installed. Mistral models will not be available.")
# except Exception as e:
#     st.warning(f"Error initializing Mistral client: {str(e)}")

# Language lists by region
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

# MEISA (Middle East, India, South Africa) Languages
meisa_languages = [
    "Afrikaans",
    "Amharic",
    "Arabic (Gulf)",
    "Arabic (Levantine)",
    "Arabic (Modern Standard)",
    "Arabic (Maghrebi)",
    "Azerbaijani",
    "Georgian",
    "Hebrew",
    "Hindi",
    "Kannada",
    "Malayalam",
    "Marathi",
    "Pashto",
    "Punjabi",
    "Somali",
    "Swahili",
    "Tamil",
    "Telugu",
    "Urdu",
    "Xhosa",
    "Zulu"
]

# LAC (Latin America and Caribbean) Languages
lac_languages = [
    "Spanish (Argentina)",
    "Spanish (Chile)",
    "Spanish (Colombia)",
    "Spanish (Mexico)",
    "Spanish (Peru)",
    "Portuguese (Brazil)",
    "Guarani",
    "Quechua",
    "Aymara",
    "Haitian Creole",
    "Jamaican Patois",
    "Nahuatl",
    "Maya",
    "Mapudungun"
]

# Combine all languages and sort alphabetically, removing duplicates
all_languages = sorted(set(european_languages + apac_languages + meisa_languages + lac_languages))

# LLM models configuration
llm_providers = {
    "Claude": {
        "models": ["claude-3-haiku-20240307", "claude-3-sonnet-20240229", "claude-3-opus-20240229", "claude-3-7-sonnet-20250219"],
        "default": "claude-3-7-sonnet-20250219"
    },
    "OpenAI": {
        "models": ["gpt-3.5-turbo", "gpt-4", "gpt-4-turbo", "gpt-4o"],
        "default": "gpt-4o"
    },
    "Gemini": {
        "models": ["gemini-pro", "gemini-1.5-pro", "gemini-1.5-flash"],
        "default": "gemini-1.5-pro"
    }
#    "Mistral": {
#        "models": ["mistral-tiny", "mistral-small", "mistral-medium", "mistral-large"],
#        "default": "mistral-large"
#    }
}

# Filter available providers based on successfully initialized clients
available_providers = list(llm_clients.keys())

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
        llm_provider TEXT NOT NULL,  -- <<< ADDED THIS LINE
        llm_model TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, -- Keep this if you want creation time
        date_added TEXT NOT NULL,    -- Keep this for the specific addition time logic used
        FOREIGN KEY (original_id) REFERENCES original_keywords (id)
    )
    ''') # Make sure the comma placement is correct before FOREIGN KEY if you modify near the end

    conn.commit()
    return conn

# Default localization prompt template
DEFAULT_PROMPT_TEMPLATE = """
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

# Function to generate a keyword localization prompt
def create_localization_prompt(keyword, category, source_language, target_language, prompt_template):
    return prompt_template.format(
        keyword=keyword,
        category=category,
        source_language=standardize_language_name(source_language),
        target_language=standardize_language_name(target_language)
    )

# Function to localize a single keyword using the selected LLM
async def localize_keyword(keyword, category, source_language, target_language, llm_provider, llm_model, prompt_template):
    prompt = create_localization_prompt(
        keyword,
        category,
        standardize_language_name(source_language),
        standardize_language_name(target_language),
        prompt_template
    )

    try:
        # Initialize result structure
        result = {
            'original_keyword': keyword,
            'category': category,
            'target_language': target_language,
            'llm_provider': llm_provider,
            'llm_model': llm_model,
            'date_added': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

        # Call the appropriate LLM based on provider selection
        if llm_provider == "Claude" and "Claude" in llm_clients:
            response = llm_clients["Claude"].messages.create(
                model=llm_model,
                max_tokens=1000,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            result_text = response.content[0].text

        elif llm_provider == "OpenAI" and "OpenAI" in llm_clients:
            # Use the openai client with proper error handling for different versions
            try:
                # Try newer client style first
                response = llm_clients["OpenAI"].chat.completions.create(
                    model=llm_model,
                    messages=[
                        {"role": "user", "content": prompt}
                    ],
                    max_tokens=1000
                )
                result_text = response.choices[0].message.content
            except AttributeError:
                # Fall back to older client style
                response = llm_clients["OpenAI"].ChatCompletion.create(
                    model=llm_model,
                    messages=[
                        {"role": "user", "content": prompt}
                    ],
                    max_tokens=1000
                )
                result_text = response.choices[0].message.content

        elif llm_provider == "Gemini" and "Gemini" in llm_clients:
            genai_model = llm_clients["Gemini"].GenerativeModel(llm_model)
            response = genai_model.generate_content(prompt)
            result_text = response.text

#        elif llm_provider == "Mistral" and "Mistral" in llm_clients:
#            # UPDATED: Using the new Mistral client API
#            response = llm_clients["Mistral"].chat(
#                model=llm_model,
#                messages=[
#                    ChatMessage(role="user", content=prompt)
#                ]
#            )
#            result_text = response.choices[0].message.content
        else:
            raise Exception(f"LLM provider {llm_provider} is not available")

        # Parse the response
        localized_keyword = None
        back_translation = None
        confidence = None
        explanation = None

        for line in result_text.split('\n'):
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

        # Update result with parsed data
        result.update({
            'localized_keyword': localized_keyword,
            'language': target_language,
            'back_translation': back_translation,
            'confidence': confidence,
            'explanation': explanation
        })

        return result

    except Exception as e:
        st.error(f"Error localizing keyword '{keyword}' with {llm_provider} {llm_model}: {str(e)}")
        return {
            'original_keyword': keyword,
            'category': category,
            'localized_keyword': f"ERROR: {str(e)}",
            'language': target_language,
            'back_translation': '',
            'confidence': 0,
            'explanation': f"Localization failed with error: {str(e)}",
            'llm_provider': llm_provider,
            'llm_model': llm_model,
            'date_added': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

# Function to process keywords in batches for multiple languages
async def process_keywords_batch(keywords_data, source_language, target_languages, llm_provider, llm_model, prompt_template):
    all_results = []

    for target_language in target_languages:
        # Prepare tasks for each keyword in each target language
        tasks = []
        for keyword_data in keywords_data:
            keyword = keyword_data.get('keyword', '')
            category = keyword_data.get('category', 'uncategorized')
            task = localize_keyword(
                keyword,
                category,
                source_language,
                target_language,
                llm_provider,
                llm_model,
                prompt_template
            )
            tasks.append(task)

        # Process in batches to avoid rate limiting
        batch_size = 5

        for i in range(0, len(tasks), batch_size):
            batch = tasks[i:i+batch_size]
            batch_results = await asyncio.gather(*batch)
            all_results.extend(batch_results)

            # Add a small delay between batches
            if i + batch_size < len(tasks):
                await asyncio.sleep(2)

    return all_results

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
            """INSERT INTO localized_keywords
               (id, original_id, localized_keyword, language, back_translation,
                confidence_score, llm_provider, llm_model, date_added)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                localized_id,
                original_id,
                result['localized_keyword'],
                result['language'],
                result['back_translation'],
                result['confidence'],
                result['llm_provider'],
                result['llm_model'],
                result['date_added']
            )
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
    # REMOVED: st.set_page_config(page_title="Advanced SEO Keyword Localizer", layout="wide")
    # Moved to top level

    st.title("Advanced SEO Keyword Localizer")
    st.markdown("""
    This tool localizes SEO keywords to different languages, preserving search intent rather than just translating words.
    Now with multiple LLM support and multi-language localization!
    """)

    # Check if any LLM provider is available
    if not available_providers:
        st.error("""
        No LLM providers are available. Please check your API keys and make sure you have the required packages installed.
        See the Settings tab for more information on configuring API keys.
        """)

    # Setup database connection
    conn = setup_database()

    # Create tabs for main functions
    tab1, tab2, tab3 = st.tabs(["Localization", "Database Explorer", "Settings"])

    with tab1:
        col1, col2 = st.columns([1, 2])

        with col1:
            st.header("Configuration")

            # Language configuration
            st.subheader("Languages")

            language_filter = st.radio(
                "Filter languages by region",
                ["All Languages", "European Languages", "APAC Languages", "MEISA Languages", "LAC Languages"],
                index=0
            )

            if language_filter == "All Languages":
                language_list = all_languages
            elif language_filter == "European Languages":
                language_list = european_languages
            elif language_filter == "APAC Languages":
                language_list = apac_languages
            elif language_filter == "MEISA Languages":
                language_list = meisa_languages
            else:  # LAC Languages
                language_list = lac_languages

            source_language = st.selectbox(
                "Source Language",
                language_list
            )

            # Filter out the source language from target options
            target_language_list = [lang for lang in language_list if lang != source_language]

            # Multiple language selection
            target_languages = st.multiselect(
                "Target Languages (select multiple)",
                target_language_list,
                default=[target_language_list[0] if target_language_list else None]
            )

            # LLM Provider and Model Selection
            st.subheader("LLM Selection")

            llm_provider = st.radio(
                "LLM Provider",
                available_providers,
                index=0 if available_providers else None,
                disabled=not available_providers
            )

            if llm_provider and llm_provider in llm_providers:
                llm_model = st.selectbox(
                    "Model",
                    llm_providers[llm_provider]["models"],
                    index=llm_providers[llm_provider]["models"].index(llm_providers[llm_provider]["default"])
                )
            else:
                llm_model = None
                st.warning("Please select an available LLM provider")

            # Prompt Tuning
            st.subheader("Prompt Tuning")
            prompt_template = st.text_area(
                "Customize Localization Prompt",
                DEFAULT_PROMPT_TEMPLATE,
                height=300
            )

            if st.button("Reset to Default Prompt"):
                prompt_template = DEFAULT_PROMPT_TEMPLATE
                st.experimental_rerun()

        with col2:
            st.header("Keywords Input")

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
            start_button_disabled = not available_providers or not llm_model
            start_processing = st.button("Start Localization", type="primary", disabled=start_button_disabled)

            if start_processing:
                if not target_languages:
                    st.error("Please select at least one target language.")
                    return # Changed from st.stop() to return for better flow control

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

                    total_tasks = len(keywords_data) * len(target_languages)
                    status_text.text(f"Localizing {len(keywords_data)} keywords from {source_language} to {len(target_languages)} languages...")

                    # Process keywords in batches for all target languages
                    try:
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        results = loop.run_until_complete(
                            process_keywords_batch(
                                keywords_data,
                                source_language,
                                target_languages,
                                llm_provider,
                                llm_model,
                                prompt_template
                            )
                        )
                        loop.close()

                        # Update progress
                        progress_bar.progress(100)
                        status_text.text(f"Localization complete! Processed {len(results)} keywords.")

                        # Display results
                        st.subheader("Localization Results")

                        # Create a more useful display dataframe
                        display_cols = ["original_keyword", "category", "language", "localized_keyword",
                                      "back_translation", "confidence", "llm_provider", "llm_model"]

                        # Handle missing columns gracefully
                        result_df = pd.DataFrame(results)
                        display_df = result_df[[col for col in display_cols if col in result_df.columns]]

                        st.dataframe(display_df, use_container_width=True)

                        # Save to database
                        save_to_database(conn, results)

                        # Export options
                        st.subheader("Export Results")
                        csv_data = export_to_csv(results)
                        timestamp = int(time.time())

                        target_langs_str = "-".join([t.split()[0] for t in target_languages])
                        if len(target_langs_str) > 30:
                            target_langs_str = "multiple-languages"

                        st.download_button(
                            label="Download CSV",
                            data=csv_data,
                            file_name=f"localized_keywords_{target_langs_str}_{timestamp}.csv",
                            mime="text/csv"
                        )
                    except Exception as e:
                        st.error(f"Error during localization process: {str(e)}")
                else:
                    st.warning("Please upload a CSV file or enter keywords manually.")

    # Database explorer tab
    with tab2:
        st.header("Database Explorer")

        # Language filter for database
        db_language_filter = st.multiselect(
            "Filter by languages",
            all_languages,
            default=[]
        )

        # LLM provider filter
        db_provider_filter = st.multiselect(
            "Filter by LLM provider",
            available_providers,
            default=[]
        )

        # Date filter
        db_date_filter = st.date_input(
            "Filter by date (from)",
            value=None
        )

        # Query button
        if st.button("Query Database"):
            cursor = conn.cursor()

            # Base query
            query = """
                SELECT
                    ok.keyword as original_keyword,
                    ok.category,
                    lk.localized_keyword,
                    lk.language,
                    lk.back_translation,
                    lk.confidence_score,
                    lk.llm_provider,
                    lk.llm_model,
                    lk.date_added
                FROM
                    localized_keywords lk
                JOIN
                    original_keywords ok ON lk.original_id = ok.id
                WHERE 1=1
            """

            # Add filters
            params = []

            if db_language_filter:
                placeholders = ",".join(["?" for _ in db_language_filter])
                query += f" AND lk.language IN ({placeholders})"
                params.extend(db_language_filter)

            if db_provider_filter:
                placeholders = ",".join(["?" for _ in db_provider_filter])
                query += f" AND lk.llm_provider IN ({placeholders})"
                params.extend(db_provider_filter)

            if db_date_filter:
                date_str = db_date_filter.strftime("%Y-%m-%d")
                query += " AND lk.date_added >= ?"
                params.append(date_str)

            query += " ORDER BY lk.date_added DESC, ok.category, ok.keyword"

            cursor.execute(query, params)
            results = cursor.fetchall()

            if results:
                columns = ["Original Keyword", "Category", "Localized Keyword", "Language",
                          "Back Translation", "Confidence", "LLM Provider", "LLM Model", "Date Added"]
                df = pd.DataFrame(results, columns=columns)
                st.dataframe(df, use_container_width=True)

                # Export database
                st.download_button(
                    label="Export Query Results to CSV",
                    data=df.to_csv(index=False),
                    file_name=f"keyword_database_export_{int(time.time())}.csv",
                    mime="text/csv"
                )
            else:
                st.info("No matching localized keywords found in the database.")

    # Settings tab
    with tab3:
        st.header("Settings")

        # API Status
        st.subheader("API Status")

        # Adjusted to 3 columns since Mistral is removed
        status_cols = st.columns(3)

        with status_cols[0]:
            if "Claude" in llm_clients:
                st.success("Claude API: Connected")
            else:
                st.error("Claude API: Not configured")

        with status_cols[1]:
            if "OpenAI" in llm_clients:
                st.success("OpenAI API: Connected")
            else:
                st.error("OpenAI API: Not configured")

        with status_cols[2]:
            if "Gemini" in llm_clients:
                st.success("Gemini API: Connected")
            else:
                st.error("Gemini API: Not configured")

#        with status_cols[3]: # Commented out Mistral status check
#            if "Mistral" in llm_clients:
#                st.success("Mistral API: Connected")
#            else:
#                st.error("Mistral API: Not configured")

        # Database management
        st.subheader("Database Management")

        col1, col2 = st.columns(2)

        with col1:
            if st.button("Clear All Database Records"):
                if 'confirm_clear' not in st.session_state:
                    st.session_state.confirm_clear = False # Initialize if not exists

                if st.session_state.get('confirm_clear', False):
                    cursor = conn.cursor()
                    cursor.execute("DELETE FROM localized_keywords")
                    cursor.execute("DELETE FROM original_keywords")
                    conn.commit()
                    st.success("Database cleared successfully!")
                    st.session_state['confirm_clear'] = False
                    st.experimental_rerun() # Rerun to clear the warning
                else:
                    st.session_state['confirm_clear'] = True
                    st.warning("Are you sure? Click the button again to confirm.")


        with col2:
            if st.button("Export Full Database"):
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT
                        ok.keyword as original_keyword,
                        ok.category,
                        lk.localized_keyword,
                        lk.language,
                        lk.back_translation,
                        lk.confidence_score,
                        lk.llm_provider,
                        lk.llm_model,
                        lk.date_added
                    FROM
                        localized_keywords lk
                    JOIN
                        original_keywords ok ON lk.original_id = ok.id
                    ORDER BY
                        lk.date_added DESC, ok.category, ok.keyword
                """)

                results = cursor.fetchall()
                if results:
                    columns = ["Original Keyword", "Category", "Localized Keyword", "Language",
                              "Back Translation", "Confidence", "LLM Provider", "LLM Model", "Date Added"]
                    df = pd.DataFrame(results, columns=columns)

                    csv_data = df.to_csv(index=False)
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

                    st.download_button(
                        label="Download Full Database CSV",
                        data=csv_data,
                        file_name=f"seo_keywords_full_db_{timestamp}.csv",
                        mime="text/csv"
                    )
                else:
                    st.info("No data in the database.")

        # API Configuration Help
        st.subheader("API Configuration")
        st.markdown("""
        To use the different LLM providers, you need to set up API keys.
        Create a `.env` file in the same directory as this script and add your keys like this:

        ```
        ANTHROPIC_API_KEY=your_claude_api_key
        OPENAI_API_KEY=your_openai_api_key
        GOOGLE_API_KEY=your_gemini_api_key
        # MISTRAL_API_KEY=your_mistral_api_key # Commented out
        ```

        Make sure you have the necessary Python packages installed:
        `pip install streamlit pandas anthropic openai google-generativeai python-dotenv uuid`
        (Note: `mistralai` is removed from the install command)
        """)

# Run the app
if __name__ == "__main__":
    main()