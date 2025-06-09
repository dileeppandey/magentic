import os
from langchain.output_parsers import PydanticOutputParser
from langchain.prompts import PromptTemplate
from langchain.chains import LLMChain
from langgraph.prebuilt import create_react_agent
from langchain_mcp_adapters.client import MultiServerMCPClient
from databricks_langchain import ChatDatabricks
from pydantic import BaseModel
import mlflow
import logging
from utils import enforce_role_alternation

mlflow.langchain.autolog()
llm = ChatDatabricks(endpoint="databricks-meta-llama-3-3-70b-instruct")
logger = logging.getLogger("naviable-agents")

class TravelSummary(BaseModel):
    markdown: str

async def setup_agents():
    client = MultiServerMCPClient({
        "nimble": {
            "url": "https://mcp.nimbleway.com/sse",
            "transport": "sse",
            "headers": {"Authorization": f"Bearer {os.getenv('NIMBLE_API_KEY')}"}
        }
    })
    tools = await client.get_tools()
    city_name_agent = create_react_agent(llm, tools, prompt="""
        You are a city name resolution agent. Convert airport codes, abbreviations, or partial city names into their full, proper city names. Return only the city name.
    """)
    flight_agent = create_react_agent(llm, tools, prompt="""
        You are a flight agent. Find the best accessible flights. Ask for missing details. Format results as markdown lists, not tables.
    """)
    lodging_agent = create_react_agent(llm, tools, prompt="""
        You are a lodging agent. Find accessible hotels/accommodations. Ask for missing details. Format results as markdown lists, not tables.
    """)
    title_agent = create_react_agent(llm, tools, prompt="""
        Summarize the following user request in 6 words or less, suitable as a chat thread title. No quotes or punctuation.
        User request: {message}
    """)
    parser = PydanticOutputParser(pydantic_object=TravelSummary)
    summary_prompt = PromptTemplate(
        input_variables=["history"],
        template=(
            "You are a travel assistant. Given the following conversation history, generate a single, user-friendly markdown summary for a travel UI. "
            "Include weather, a markdown list of flight and hotel options, accessibility features, and any follow-up questions. "
            "Do not use markdown tables. Do not include the user's original question or any code blocks or JSON in the markdown.\n"
            "\nReturn your answer as a JSON object with a single field 'markdown' whose value is the markdown string.\n"
            "Example:\n"
            '{{"markdown": "# Weather\\n* San Francisco: ...\\n* Los Angeles: ...\\n## Flights\\n- Airline: ...\\n- Price: ...\\n- Dates: ...\\n- Accessibility: ...\\n## Hotels\\n- Hotel: ...\\n- Price: ...\\n- Dates: ...\\n- Accessibility: ..."}}'
            "\n\nConversation history:\n{history}"
        )
    )
    summary_chain = LLMChain(llm=llm, prompt=summary_prompt, output_parser=parser)
    async def supervisor_agent(messages):
        from copy import deepcopy
        alternated_messages = enforce_role_alternation(deepcopy(messages))
        logger.info(f"Sending to agent, alternated messages: {alternated_messages}")
        user_content = alternated_messages[-1]['content'].lower()
        flight_keywords = ['flight', 'fly', 'ticket', 'airline', 'airport', 'depart', 'arrive']
        lodging_keywords = ['hotel', 'lodging', 'accommodation', 'stay', 'inn', 'motel', 'hostel', 'bnb', 'room']
        is_flight_query = any(keyword in user_content for keyword in flight_keywords)
        is_lodging_query = any(keyword in user_content for keyword in lodging_keywords)
        if is_flight_query:
            logger.info("Invoking flight_agent for this query.")
            return await flight_agent.ainvoke({"messages": alternated_messages})
        elif is_lodging_query:
            logger.info("Invoking lodging_agent for this query.")
            return await lodging_agent.ainvoke({"messages": alternated_messages})
        else:
            logger.info("Invoking base LLM for this query.")
            return await llm.ainvoke(alternated_messages)
    return supervisor_agent, summary_chain, title_agent

# Synchronous wrapper for Flask
import asyncio as _asyncio
_supervisor_agent, _summary_chain, _title_agent = _asyncio.run(setup_agents())
supervisor_agent = _supervisor_agent
summary_chain = _summary_chain
title_agent = _title_agent 