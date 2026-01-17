#!/usr/bin/env python3
import os
import sys
import logging

from git_analyzer import GitAnalyzer
from code_parser import CodeParser
from llm_client import LLMClient, create_client
from scenario_generator import ScenarioGenerator
from github_commenter import GitHubCommenter
from review_generator import ReviewGenerator
from github_reviewer import GitHubReviewer
from description_generator import DescriptionGenerator

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def run_scenario_generation(
    pr_info,
    code_context: str,
    openai_api_key: str,
    model: str,
    language: str,
    github_token: str
):
    """Run test scenario generation and post as PR comment."""
    logger.info(f"Generating test scenarios with {model}...")
    llm_client = LLMClient(openai_api_key, model)
    generator = ScenarioGenerator(llm_client, language)
    result = generator.generate(code_context, len(pr_info.files))

    logger.info(f"Generated {len(result.scenarios)} scenarios")
    logger.info(f"API usage: {llm_client.format_cost_info(result.llm_response)}")

    # Post comment to PR
    logger.info("Posting scenario comment to PR...")
    commenter = GitHubCommenter(github_token)
    comment_url = commenter.post_from_env(result, language)

    if comment_url:
        logger.info(f"Scenario comment posted: {comment_url}")
    else:
        logger.warning("Could not post scenario comment (not in PR context)")


def run_description_generation(
    pr_info,
    code_context: str,
    api_key: str,
    model: str,
    language: str,
    github_token: str
):
    """Generate PR description and append to PR body."""
    logger.info(f"Generating PR description with {model}...")

    llm_client = LLMClient(api_key, model)
    generator = DescriptionGenerator(llm_client, language)
    result = generator.generate(code_context, len(pr_info.files))

    logger.info(f"Generated PR description")
    logger.info(f"API usage: {llm_client.format_cost_info(result.llm_response)}")

    # Format and update PR description
    description_text = generator.format_description(result)
    commenter = GitHubCommenter(github_token)
    pr_url = commenter.update_pr_description_from_env(description_text)

    if pr_url:
        logger.info(f"PR description updated: {pr_url}")
    else:
        logger.warning("Could not update PR description (not in PR context)")


def run_code_review(
    pr_info,
    code_context: str,
    review_engine: str,
    review_model: str,
    api_key: str,
    language: str,
    github_token: str
):
    """Run code review and post as PR review with line comments."""
    logger.info(f"Generating code review with {review_engine}/{review_model}...")

    # Create appropriate LLM client based on engine
    llm_client = create_client(review_engine, api_key, review_model)
    generator = ReviewGenerator(llm_client, language)
    result = generator.generate(code_context, len(pr_info.files))

    logger.info(f"Generated {len(result.comments)} review comments")
    logger.info(f"API usage: {llm_client.format_cost_info(result.llm_response)}")

    # Post review to PR
    logger.info("Posting code review to PR...")
    reviewer = GitHubReviewer(github_token)
    review_url = reviewer.post_from_env(result, language)

    if review_url:
        logger.info(f"Code review posted: {review_url}")
    else:
        logger.warning("Could not post code review (not in PR context)")


def main():
    # Get configuration from environment
    github_token = os.environ.get('GITHUB_TOKEN')
    openai_api_key = os.environ.get('OPENAI_API_KEY')
    anthropic_api_key = os.environ.get('ANTHROPIC_API_KEY')
    model = os.environ.get('MODEL', 'gpt-4o')
    language = os.environ.get('LANGUAGE', 'ko')
    max_files = int(os.environ.get('MAX_FILES', '50'))
    mode = os.environ.get('MODE', 'both')
    review_engine = os.environ.get('REVIEW_ENGINE', 'openai')
    review_model = os.environ.get('REVIEW_MODEL', 'gpt-4o')
    generate_description = os.environ.get('GENERATE_DESCRIPTION', 'false').lower() == 'true'

    if not github_token:
        logger.error("GITHUB_TOKEN is required")
        sys.exit(1)

    # Validate API keys based on mode and engine
    needs_openai = mode in ('scenario', 'both') or (mode in ('review', 'both') and review_engine == 'openai') or generate_description
    needs_anthropic = mode in ('review', 'both') and review_engine == 'claude'

    if needs_openai and not openai_api_key:
        logger.error("OPENAI_API_KEY is required for scenario generation or OpenAI review")
        sys.exit(1)

    if needs_anthropic and not anthropic_api_key:
        logger.error("ANTHROPIC_API_KEY is required for Claude review")
        sys.exit(1)

    logger.info(f"Starting (mode: {mode}, scenario_model: {model}, review_engine: {review_engine}/{review_model}, language: {language})")

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

        if pr_info.is_draft:
            logger.info("PR is draft, skipping analysis")
            sys.exit(0)

        if not pr_info.files:
            logger.info("No files changed, skipping analysis")
            sys.exit(0)

        # Step 2: Parse code changes
        logger.info("Parsing code changes...")
        parser = CodeParser()
        parsed_changes = parser.parse_changes(pr_info)
        code_context = parser.format_for_llm(parsed_changes, pr_info)

        logger.info(f"Parsed {len(parsed_changes)} files")

        # Step 3: Execute based on mode
        if mode in ('scenario', 'both'):
            run_scenario_generation(
                pr_info=pr_info,
                code_context=code_context,
                openai_api_key=openai_api_key,
                model=model,
                language=language,
                github_token=github_token
            )

        if mode in ('review', 'both'):
            # Determine which API key to use for review
            if review_engine == 'claude':
                api_key = anthropic_api_key
            else:
                api_key = openai_api_key

            run_code_review(
                pr_info=pr_info,
                code_context=code_context,
                review_engine=review_engine,
                review_model=review_model,
                api_key=api_key,
                language=language,
                github_token=github_token
            )

        if generate_description:
            run_description_generation(
                pr_info=pr_info,
                code_context=code_context,
                api_key=openai_api_key,
                model=model,
                language=language,
                github_token=github_token
            )

        logger.info("Done!")

    except Exception as e:
        logger.error(f"Error: {e}")
        raise


if __name__ == '__main__':
    main()
