import re

with open('plumber/vault-harvester.py', 'r') as f:
    text = f.read()

text = text.replace('md += f"| **{p[\'name\']}** | {p[\'status\']} | {tech_str} | {health_icon} {p[\'health\']} | {p[\'recent_commits\']} | {p[\'todo_count\']} |\n"', 'md += f"| **{p[\'name\']}** | {p[\'status\']} | {tech_str} | {health_icon} {p[\'health\']} | {p[\'recent_commits\']} | {p[\'todo_count\']} |\\n"')
text = text.replace('md += "\n## Project Details\n\n"', 'md += "\\n## Project Details\\n\\n"')
text = text.replace('md += f"- **Description:** {p[\'description\'][:120]}\n"', 'md += f"- **Description:** {p[\'description\'][:120]}\\n"')
text = text.replace('md += f"- **Stack:** {\', \'.join(p[\'tech\'][:5])}\n"', 'md += f"- **Stack:** {\', \'.join(p[\'tech\'][:5])}\\n"')
text = text.replace('md += "- **Issues:**\n"', 'md += "- **Issues:**\\n"')
text = text.replace('md += f"  - ⚠️ {issue}\n"', 'md += f"  - ⚠️ {issue}\\n"')
text = text.replace('md += f"- **Recent activity:** {p[\'recent_commits\']} commits in last 7 days\n"', 'md += f"- **Recent activity:** {p[\'recent_commits\']} commits in last 7 days\\n"')
text = text.replace('md += f"- **Open items:** {p[\'todo_count\']} TODOs/FIXMEs\n"', 'md += f"- **Open items:** {p[\'todo_count\']} TODOs/FIXMEs\\n"')
text = text.replace('md += "\n"', 'md += "\\n"')
text = text.replace('md += "## Cross-Project Tech Stack\n"', 'md += "## Cross-Project Tech Stack\\n"')
text = text.replace('md += "| Technology | Used In | Projects |\n"', 'md += "| Technology | Used In | Projects |\\n"')
text = text.replace('md += "|------------|---------|----------|\n"', 'md += "|------------|---------|----------|\\n"')
text = text.replace('md += f"| {tech} | {len(projs)} | {\', \'.join(projs[:3])}{\'...\' if len(projs) > 3 else \'\'} |\n"', 'md += f"| {tech} | {len(projs)} | {\', \'.join(projs[:3])}{\'...\' if len(projs) > 3 else \'\'} |\\n"')
text = text.replace('md += "## Recent Activity (7 Days)\n"', 'md += "## Recent Activity (7 Days)\\n"')
text = text.replace('md += f"- **{proj}:** {count} commits\n"', 'md += f"- **{proj}:** {count} commits\\n"')
text = text.replace('md += "## Cross-Project Open Items\n"', 'md += "## Cross-Project Open Items\\n"')
text = text.replace('md += f"- **[{todo[\'kind\']}]** {todo[\'desc\']} — *{todo[\'project\']}*\n"', 'md += f"- **[{todo[\'kind\']}]** {todo[\'desc\']} — *{todo[\'project\']}*\\n"')
text = text.replace('md += f"\n_... and {len(all_todos) - 20} more_\n"', 'md += f"\\n_... and {len(all_todos) - 20} more_\\n"')
text = text.replace('md += "\n".join(suggestions) + "\n"', 'md += "\\n".join(suggestions) + "\\n"')

with open('plumber/vault-harvester.py', 'w') as f:
    f.write(text)

