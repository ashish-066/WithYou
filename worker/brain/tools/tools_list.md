## Tools List

1.Crawler
    - 2 Tools -> Slow and fast
    - Fast: crawler API, Slow : custom script that you will make
    - GItHub ( publicly owned - not forked repositories ), LinkedIn, Resume ( hackathons and workshops are niche ), and convert the whole data into a json file.
2.Speech confidence ( 2 tools )
    - Get resources to calculate confidence
    - Take input from previous tool and calculate the confidence level
3.Fill rubric - Create a rubric table ( should have well defined columns and rows ) and leave spaces to fill it ( the llm will fill that )
4.Tavly search
    - Just implement it, you can import and assume a string as input, ( give your own input for testing )
5.Citation marker
    - Note down important timestamp - it is later useful for making final evaluation ( also used in dashboard )
6.Final evaluation
    - 2 tools, one for final report paragraph and one for returning graph data for the dashboard Tool
    1) Takes the output from crawler, speech confidence and rubric and gives a final score out of 100 ( score is an LLM call, so all you need is to fetch and store the overall data neatly in this function )
