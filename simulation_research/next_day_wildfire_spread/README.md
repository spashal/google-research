# Next Day Wildfire Spread: A Machine Learning Data Set to Predict Wildfire Spreading from Remote-Sensing Data

This is the code accompanying the paper ["Next Day Wildfire Spread: A Machine Learning Data Set to Predict Wildfire Spreading from Remote-Sensing Data"](http://arxiv.org/abs/2112.02447).

The dataset can be found on [Kaggle](https://www.kaggle.com/fantineh/next-day-wildfire-spread).

If you use this code or data, please cite:

F. Huot, R. L. Hu, N. Goyal, T. Sankar, M. Ihme, and Y.-F. Chen, “Next Day Wildfire Spread: A Machine Learning Data Set to Predict Wildfire Spreading from Remote-Sensing Data”, arXiv preprint, 2021.

## Data Demo

dataset_demo.ipynb is a Jupyter Notebook demonstrating how to load and parse the data set.

## Data Export

To export the data yourself, ensure you have a Google Storage bucket. Here is
an example command, substituting your own bucket.

```
python3 -m simulation_research.wildfire_prediction.export_ee_training_data_main \
--bucket=${BUCKET} \
--start_date="2020-01-01" \
--end_date="2021-01-01"
```
