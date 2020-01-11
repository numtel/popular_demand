# Popular Demand

Very much not production ready

> Branded as UnitedConsumersOfAmerica.com [Original gist](https://gist.github.com/numtel/5156fb61da89862aaa5160a2a02dde89) [Consumer Union Manifesto](https://gist.github.com/numtel/380d391ed5b324fc645a30a91a768550)

A moderated, threaded discussion board using Django with crowdfunding functionality through Stripe

The interface utilizes a threaded discussion board to collect funds under
individual messages in order to show support for a solution to the idea
proposed within the message, while waiting for bids to be submitted. These
bids may then be funded by the migration of funds from the original
message to the bid message. The bidder receives the payment when their
bid-specified payment threshold is met.

The live demo at UnitedConsumersOfAmerica.com has crowdfunding disabled because Stripe didn't accept my Atlas application.

## Installation

1. Configure Stripe details in `docker-compose.yml` if enabling crowdfunding.
2. Launch the server and a Postgres instance in Docker:
    ```
    docker-compose up
    ```
3. Install database tables
    ```
    docker exec -it popular_demand_app_1 bash
    bash-4.3# python manage.py migrate
    ```
3. Browse to the new instance:
    ```
    http://localhost:8000
    ```
    You will be prompted to Join. The first user created is automatically a moderator. You may need to create a seperate superuser to access the Django admin. After logging in, you will be prompted to create the root post, to which all other messages reply.

## Todo

* Moderation assignment by root message instead of global user group
* Mas pruebas

