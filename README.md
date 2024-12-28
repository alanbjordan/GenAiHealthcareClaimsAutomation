# Medical Record Analysis

## Project Overview

This repository contains the `Medical Record Analysis` project, designed to analyze military service and post-service medical records to classify potential disabilities. It leverages Natural Language Processing (NLP) techniques and the OpenAI GPT model to extract, analyze, and compare diagnoses documented in the records, ensuring each diagnosis is supported by evidence from both in-service and post-service records.

## Key Features

- **PDF Text Extraction**: Extracts text from PDF files of medical records.
- **NLP Analysis**: Uses spaCy and OpenAI's GPT models to classify text data into medical diagnoses.
- **Token Efficiency**: Ensures efficient processing by managing token limits in API requests.
- **Comparison Logic**: Identifies and lists diagnoses that have supporting evidence in both sets of records.

## Installation

Clone the repository to your local machine:

```bash
git clone https://github.com/yourusername/MedicalRecordAnalysis.git
cd MedicalRecordAnalysis
```

Install the required dependencies:

```bash
pip install -r requirements.txt
```

## Usage

To run the analysis, execute the main script:

```bash
python analyze_records.py
```

Ensure you have the necessary PDF files in the project directory or specify their paths in the script.

## Configuration

Before running the script, set up the following:

- **API Key**: Ensure your OpenAI API key is set in your environment variables or specified directly in the script.
- **Model Configuration**: Adjust the OpenAI model settings as needed to fit the complexity of your text analysis.

## Contributing

Contributions to the `Medical Record Analysis` project are welcome. Please ensure to follow the existing coding style, add unit tests for any new functionality, and document your code appropriately.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Authors

- **Alan Jordan** - *Initial work* - [alanbjordan](https://github.com/alanbjordan)

## Acknowledgments

- Thanks to OpenAI for providing the API used in this project.
- Appreciation to contributors who discuss and enhance this project.

