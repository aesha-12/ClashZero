# Install dependencies
pip install -r requirements.txt

# Run demo (creates DB, generates data, exports for algorithm)
python main.py --demo

# Or step by step:
python main.py --init                    # Create tables
python main.py --generate medium         # Generate test data
python main.py --stats                   # View statistics
python main.py --export                  # Create algorithm_input.json
