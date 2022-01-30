# Online Shop
To quick start with docker:

   1. Clone this repository:
       ```bash
      git clone git clone https://github.com/SkrytnayaRediska/online_shop.git
      ```
    
   2. Build and start docker container
         ```bash
         docker-compose up --build
         ```
Default superuser will have email test@test and password 123456789
   

Without docker:
  1. Create database with name **shop**
  2. Go to the project folder
       ```bash
        cd online_shop
        ```
  3. If you don't have a poetry:
     ```bash
     pip3 install poetry
     ```
  4. Install poetry dependencies
     ```bash
      poetry install
      ```
  5. Apply migrations
      ```bash
       poetry run python3 manage.py makemigrations
       poetry run python3 manage.py migrate
      ```
  6. Create superuser
     ```bash
       poetry run python3 manage.py createsuperuser
      ```
  7. Run the app
      ```bash
      poetry run python3 manage.py runserver
      ```
     

You can test this app with postman requests collection (it is in **_/additional_** folder)
