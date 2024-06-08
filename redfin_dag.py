from airflow import DAG
from datetime import timedelta, datetime
from airflow.operators.python import PythonOperator
import pandas as pd
import boto3
from airflow.operators.bash_operator import BashOperator

url_by_city="https://redfin-public-data.s3.us-west-2.amazonaws.com/redfin_market_tracker/city_market_tracker.tsv000.gz"

s3_client = boto3.client('s3')

# s3 buckets
target_bucket_name = 'redfindata-bucket/Transformed_data/'

def extract_data(**kwargs):
    url = kwargs['url']
    df = pd.read_csv(url, compression='gzip', sep='\t')
    now = datetime.now()
    date_now_string = now.strftime("%Y-%m-%d %H:%M:%S")
    file_str = 'redfin_data_' + date_now_string
    df.to_csv(f"{file_str}.csv", index=False)
    output_file_path = f"/home/ubuntu/Ankur_Projects/RedFin/{file_str}.csv"
    output_list = [output_file_path, file_str]
    return output_list

def transform_data(task_instance):
    data = task_instance.xcom_pull(task_ids="tsk_extract_redfin_data")[0]
    object_key = task_instance.xcom_pull(task_ids="tsk_extract_redfin_data")[1]
    df = pd.read_csv(data)

    # Remove commas from the 'city' column
    df['city'] = df['city'].str.replace(',', '')
    cols = ['period_begin','period_end','period_duration', 'region_type', 'region_type_id', 'table_id',
    'is_seasonally_adjusted', 'city', 'state', 'state_code', 'property_type', 'property_type_id',
    'median_sale_price', 'median_list_price', 'median_ppsf', 'median_list_ppsf', 'homes_sold',
    'inventory', 'months_of_supply', 'median_dom', 'avg_sale_to_list', 'sold_above_list', 'parent_metro_region_metro_code', 'last_updated']
   
    df = df[cols]
    df = df.dropna()

    #let's change the period_begin and period_end to date time object and extract years and month.
    df['period_begin'] = pd.to_datetime(df['period_begin'])
    df['period_end'] = pd.to_datetime(df['period_end'])

    df["period_begin_in_years"] = df['period_begin'].dt.year
    df["period_end_in_years"] = df['period_end'].dt.year

    df["period_begin_in_months"] = df['period_begin'].dt.month
    df["period_end_in_months"] = df['period_end'].dt.month
    
    #let's map the month number to their respective month name.
    month_dict = {
        "period_begin_in_months": {
            1 : "Jan",2 :  "Feb",3: "Mar",4: "Apr",5: "May",6: "Jun",7: "Jul",8: "Aug",9: "Sep",10: "Oct",11: "Nov",12: "Dec",
        },
        "period_end_in_months": {
            1 : "Jan",2 :  "Feb",3: "Mar",4: "Apr",5: "May",6: "Jun",7: "Jul",8: "Aug",9: "Sep",10: "Oct",11: "Nov",12: "Dec"
        }}
    
    df = df.replace(month_dict)
    print('Num of rows:', len(df))
    print('Num of cols:', len(df.columns))
        
    # Convert DataFrame to CSV format
    csv_data = df.to_csv(index=False)
        
    # Upload CSV to S3
    object_key = f"{object_key}.csv"
    s3_client.put_object(Bucket=target_bucket_name, Key=object_key, Body=csv_data)



default_args = {
    'owner': 'airflow',
    'depends_on_past': False,
    'start_date': datetime(2024, 5, 25),
    'email': ['xyz@gmail.com'],
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 2,
    'retry_delay': timedelta(seconds=10)
}

with DAG('Redfin_dag',
         default_args=default_args,
         schedule_interval='@weekly',
         catchup=False) as dag:
    
    extract_redfin_data = PythonOperator(
        task_id= 'tsk_extract_redfin_data',
        python_callable=extract_data,
        op_kwargs={'url': url_by_city}
        )
    
    transform_redfin_data = PythonOperator(
        task_id= 'tsk_transform_redfin_data',
        python_callable=transform_data
        )
    
    load_redfin_data_to_S3 = BashOperator(
            task_id = 'tsk_load_redfin_data_to_S3',
            bash_command = 'aws s3 mv {{ ti.xcom_pull("tsk_extract_redfin_data")[0]}} s3://redfindata-bucket/Raw_data/',
        )
    
    extract_redfin_data >> transform_redfin_data >> load_redfin_data_to_S3