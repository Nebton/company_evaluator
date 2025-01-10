from openai import OpenAI
import json
import logging
import argparse
from typing import List, Dict, Any
from time import sleep
import re
from dotenv import load_dotenv
import os

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('job_search.log'),
        logging.StreamHandler()
    ]
)

def validate_job_title(job_title: str) -> str:
    """Validate the job title input"""
    if not job_title or job_title == "define-your-job-here":
        raise ValueError("Please define a valid job title")
    return job_title

def parse_args() -> argparse.Namespace:
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description='Analyze companies for job opportunities')
    parser.add_argument('--job', required=True, help='Job title to search for')
    parser.add_argument('--batch-size', type=int, default=30, help='Number of companies per batch')
    parser.add_argument('--model', default='gpt-4o-mini', help='OpenAI model to use')
    parser.add_argument('--output-format', choices=['json', 'csv'], default='json', help='Output format')
    return parser.parse_args()

def extract_json_from_response(response_text: str) -> str:
    """Extract JSON from markdown code blocks in the response"""
    json_match = re.search(r'```json\n(.*?)\n```', response_text, re.DOTALL)
    if json_match:
        return json_match.group(1)
    return response_text

def rate_limit_handler(batch_size: int, total_processed: int) -> None:
    """Handle rate limiting and cost estimation"""
    estimated_cost = (total_processed / batch_size) * 0.01
    logging.info(f"Estimated cost so far: ${estimated_cost:.2f}")
    sleep(2)

def save_results(results: List[Dict[str, Any]], format: str = 'json') -> None:
    """Save results in the specified format"""
    if format == 'json':
        output_file = 'sorted_company_scores.json'
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        logging.info(f"Results saved to {output_file}")
    elif format == 'csv':
        output_file = 'sorted_company_scores.csv'
        import csv
        with open(output_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=['company_name', 'score', 'explanation'])
            writer.writeheader()
            writer.writerows(results)
        logging.info(f"Results saved to {output_file}")

def analyze_batch(client: OpenAI, companies_batch: List[Dict[str, str]], batch_num: int, job: str, model: str) -> Dict[str, Any]:
    """Analyze a single batch of companies using GPT-4"""
    companies_text = "\n\n".join(
        f"Company {i+1}: {company['company']}\n{company['about']}"
        for i, company in enumerate(companies_batch)
    )
    
    prompt = f"""Evaluate these companies based on their mission and potential need for a {job}.
For each company, provide a score from 0-100 and a brief explanation in French.

Companies:
{companies_text}

Respond in this JSON format:
{{
    "analyses": [
        {{
            "company_name": "<name>",
            "score": <0-100>,
            "explanation": "<brief explanation in French>"
        }},
        ...
    ]
}}"""

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": f"You are a technical recruiter specializing in {job} positions."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7
        )
        response_text = response.choices[0].message.content
        json_str = extract_json_from_response(response_text)
        return json.loads(json_str)

    except Exception as e:
        logging.error(f"Error in batch {batch_num}: {str(e)}")
        return None

def main() -> None:
    # Load environment variables
    load_dotenv()
    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key:
        raise ValueError("OPENAI_API_KEY not found in environment variables")

    # Parse arguments
    args = parse_args()
    job = validate_job_title(args.job)
    # File containing companies' information
    file="f_station.json"
    # Initialize OpenAI client
    client = OpenAI(api_key=api_key)
    
    try:
        # Load companies
        with open(file, 'r', encoding='utf-8') as f:
            companies = json.load(f)
        
        logging.info(f"Loaded {len(companies)} companies")
        
        # Initialize variables
        current_batch = []
        all_results = []
        batch_num = 1
        
        # Process companies
        for i, company in enumerate(companies):
            current_batch.append(company)
            
            # When we reach batch_size or it's the last company, process the batch
            if len(current_batch) == args.batch_size or i == len(companies) - 1:
                logging.info(f"Processing batch {batch_num} ({len(current_batch)} companies)")
                
                # Analyze the batch
                result = analyze_batch(client, current_batch, batch_num, job, args.model)
                
                if result:
                    all_results.extend(result['analyses'])
                    
                    # Save progress after each successful batch
                    save_results(all_results, args.output_format)
                    logging.info(f"Processed batch {batch_num} successfully")
                
                # Reset for next batch
                current_batch = []
                batch_num += 1
                
                # Rate limiting
                if i < len(companies) - 1:
                    rate_limit_handler(args.batch_size, i + 1)
        
        # Sort and display top results
        sorted_results = sorted(all_results, key=lambda x: x['score'], reverse=True)
        save_results(sorted_results, args.output_format)

        logging.info("\n=== Top 10 Companies ===")
        for result in sorted_results[:10]:
            logging.info(f"\nCompany: {result['company_name']}")
            logging.info(f"Score: {result['score']}")
            logging.info(f"Explanation: {result['explanation']}")

    except Exception as e:
        logging.error(f"Error in main execution: {str(e)}")
        raise

if __name__ == "__main__":
    main()
