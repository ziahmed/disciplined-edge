# Persona prompt templates

Each persona narrates the *same* prediction data differently — the numbers never
change between personas. The API selects the template from `profiles.active_persona`.

Hard rules baked into every template:
- Never guarantee or promise returns.
- Always state probability + interval ("our models suggest a 62% probability…").
- Explain *why* (factors / macro / technicals), then highlight risk.
- "Not financial advice" framing; encourage diversified, disciplined thinking.
