## overview

- bud is an application to help users manage their expenses and monthly budgets
- it has both a cli and an api
- is built to be used in agentic worflows, where the user interacts with it through some messaging channel (like whatsapp or telegram), and the remote agent uses bud as a tool

## features

- the system should allow the user to create an user account through the cli or the api
- the system should allow the user create an user account linked to my google account 
- the system should allow the user to authenticate using some token that can be stored in the filesystem
- the system should allow the user to authenticate using his google account
- the system should allow the user to create transactions
- the system should allow the user to update transactions
- the system should allow the user to delete transactions
- the system should allow the user to retrieve transactions details
- the system should allow the user to list transactions of a given month 
- the system should allow the user to set the active month to avoid passing it as argument on every operation
- the system should allow the user to create a budget for a given month
- the system should allow the user to edit a budget for a given month
- the system should allow the user to delete a budget for a given month
- the system should allow the user to create forecasts for a given budget
- the system should allow the user to edit forecasts for a given budget
- the system should allow the user to delete forecasts for a given budget
- the system should allow the user to get a report of the budget for a given month
- the system should allow the user to create accounts
- the system should allow the user to edit accounts
- the system should allow the user to delete accounts
- the system should allow the user to list accounts
- the system should allow the user to manage categories (create, delete, edit, list)
- the system should allow the user to manage projects (create, delete, edit, list)
- the system should allow the user to set the default project

## domain

- projects
    - the user always has at least one project (main project)
    - have a name
    - have a collection of accounts, that can be related to multiple projects

- transactions
    - have an id
    - have a value
    - have a description
    - have a source account
    - have a destination account
    - have a category
    - have tags
    - every transaction has its counterpart, which has inverse value, and source and destination accounts are switched
    
- accounts
    - have an id
    - have a name
    - have a type (credit / debit / nil)
    - there is one special account (nil) that represents an external source/destination
    - can be related to one or more project

- budgets
    - have an id
    - have a name
    - have a start date and an end date
    - currently there are only monthly budgets, but in theory start and end could be relative to any period
    - have a name (YYYY-MM)
    - belongs to a specific project
    - have a collection of forecasts

- forecasts
    - have an id
    - have a description
    - belongs to a budget
    - have a value
    - can have a category
    - can have tags
    - can have a min value
    - can have a max value
    - can be recurrent (start/end or permanent)

- reports
    - are related to a specific budget
    - show the balance of each account at the end of the period of the budget
    - show the total balance, total expenses and total earnings
    - show all the forecasts and the actual/expected values
    - reports for budgets ahead should calculate the expected balance based on the current budget projecting each monthly budget until the report month

## architectural characteristics

- should be written in python
- should have a cli interface using click
- should have an api using fastapi
- should use uv
- should access a postgres database using sqlalchemy
- should be run in a docker container
- should have a makefile with venv, setup, build, test, watch
