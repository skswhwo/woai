#!/usr/bin/env python3
import os
import sys
import logging

from git_analyzer import GitAnalyzer
from code_parser import CodeParser
from llm_client import LLMClient
from scenario_generator import ScenarioGenerator
from github_commenter import GitHubCommenter

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    # Get configuration from environment
    github_token = os.environ.get('GITHUB_TOKEN')
    openai_api_key = os.environ.get('OPENAI_API_KEY')
    model = os.environ.get('MODEL', 'o3-mini')
    language = os.environ.get('LANGUAGE', 'ko')
    max_files = int(os.environ.get('MAX_FILES', '20'))

    if not github_token:
        logger.error("GITHUB_TOKEN is required")
        sys.exit(1)

    if not openai_api_key:
        logger.error("OPENAI_API_KEY is required")
        sys.exit(1)

    logger.info(f"Starting test scenario extraction (model: {model}, language: {language})")

    try:
        # Step 1: Analyze PR
        logger.info("Analyzing PR...")
        git_analyzer = GitAnalyzer(github_token)
        pr_info = git_analyzer.get_pr_from_env(max_files)

        if not pr_info:
            logger.error("Could not get PR information from environment")
            sys.exit(1)

        logger.info(f"PR #{pr_info.number}: {pr_info.title}")
        logger.info(f"Files changed: {len(pr_info.files)}")

        if not pr_info.files:
            logger.info("No files changed, skipping analysis")
            sys.exit(0)

        # Step 2: Parse code changes
        logger.info("Parsing code changes...")
        parser = CodeParser()
        parsed_changes = parser.parse_changes(pr_info)
        code_context = parser.format_for_llm(parsed_changes, pr_info)

        logger.info(f"Parsed {len(parsed_changes)} files")

        # Step 3: Generate scenarios with LLM
        logger.info(f"Generating test scenarios with {model}...")
        llm_client = LLMClient(openai_api_key, model)
        generator = ScenarioGenerator(llm_client, language)
        result = generator.generate(code_context, len(pr_info.files))

        logger.info(f"Generated {len(result.scenarios)} scenarios")
        logger.info(f"API usage: {llm_client.format_cost_info(result.llm_response)}")

        # Step 4: Post comment to PR
        logger.info("Posting comment to PR...")
        commenter = GitHubCommenter(github_token)
        comment_url = commenter.post_from_env(result, language)

        if comment_url:
            logger.info(f"Comment posted: {comment_url}")
        else:
            logger.warning("Could not post comment (not in PR context)")

        logger.info("Done!")

    except Exception as e:
        logger.error(f"Error: {e}")
        raise


if __name__ == '__main__':
    main()
