# Automated Cold Outreach Pipeline

A fully automated cold outreach pipeline that takes a single company 
domain as input and handles everything from finding similar companies 
to sending personalized outreach emails — zero manual steps.

## How It Works

One input. Four stages. A full outreach engine.

- Stage 1 — Ocean.io: Takes a seed domain and finds 10 similar 
  companies with matching firmographics
- Stage 2 — Prospeo: Finds C-suite and VP-level decision makers 
  at each company along with their LinkedIn URLs
- Stage 3 — Email Filter: Filters contacts to only those with 
  verified work emails
- Stage 4 — Brevo: Sends each contact a personalized outreach 
  email automatically

Every stage's output is the next stage's input. No human touches 
the data in between.

## Setup

1. Clone the repository
   git clone https://github.com/Ananyaya17/Automated-Outreach-Pipeline.git
   cd Automated-Outreach-Pipeline

2. Install dependencies
   pip install -r requirements.txt

3. Create a .env file using .env.example as a template
   OCEAN_API_KEY=your_ocean_api_key
   PROSPEO_API_KEY=your_prospeo_api_key
   BREVO_API_KEY=your_brevo_api_key
   BREVO_SENDER_EMAIL=your_verified_sender@yourdomain.com

## Usage

Dry run (no emails actually sent):
   python main.py --dry-run

Live run (emails will be sent):
   python main.py

## API Keys Required

- Ocean.io — company lookalike search
- Prospeo — decision maker and email finder
- Brevo — email sending platform

## Tech Stack

- Python 3.10+
- Ocean.io API
- Prospeo API
- Brevo API
- Rich (terminal UI)
