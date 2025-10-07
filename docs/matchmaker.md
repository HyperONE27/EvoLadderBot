Here's the description of the matchmaking algorithm I want to implement:

- When a player queues, the matchmaker should create an object corresponding to them and add it to the matchmaking queue.
    - The object should contain their Discord ID (exactly 1), race selections (at least 1, up to 2, no more than 1 BW race and 1 SC2 race), and map vetoes (no more than 4)
    - The object should also contain:
        - MMR for each of the selected races, looked up from the database
        - How long they have been waiting in the queue
- The validity of a potential match depends on two factors:
    - All matches should be BW vs SC2, never BW vs BW or SC2 vs SC2
        - Players can queue with 1 BW race and 1 SC2 race, so we should be careful not to match players with themselves
    - The difference between
        - We will use an elastic window to permit greater differences between matches if at least one of the players has been waiting long enough

The way we will actually create matches, given a bunch of players, is as follows:
- There will be a bunch of players queueing for the ladder. Maintain three lists, sorted from highest MMR to lowest MMR:
    - (List X): Players who queue with a BW race only
    - (List Y): Players who queue with an SC2 race only
    - (List Z): Players who queue with both BW and SC2
- Every X seconds, the matchmaker will attempt to create a wave of matches. At each wave:
    - 1. Dump a COPY of List Z into Lists X and Y to equalize their sizes (we want to keep List Z as it is in case players don't get matched)
        - Get the difference in the cardinality of Lists X and Y
        - Without loss of generality, consider the case where List X has fewer players than List Y:
            - If mean(X) < mean(Y), push the highest-rated player in Z to X
            - If mean(X) > mean(Y), push the lowest-rated player in Z to X
            - Keep recalculating means and pushing players from Z to X until X and Y have equal numbers of players
                - If they reach event count, just keep going, alternating assignment between X and Y
                - If they never reach even count, ignore this
    - 2. Between Lists X and Y, choose the smaller list as the "lead" side
        - The other list becomes the "follow" side
    - 3. Calculate the mean MMR of the lead side
    - 4. Calculate the priority of each player
        - priority = (distance from mean MMR) + (10 x number of matching cycles waited)
    - 5. Sort the lead side from highest to lowest priority
    - 6. Going from highest to lowest priority, calculate the maximum tolerable MMR difference for that player
        - MMR_delta will be a custom function:
            ```python
            """
            max_diff() returns the maximum acceptable MMR difference between a lead side player and a follow side player when queueing.

            This is only calculated for the lead side; the max_diff() value for the follow side player doesn't matter,
            i.e. if a high-rating player has been waiting a long time then they can queue with a much lower-rated player
            even if that lower-rated player just joined the queue.

            We scale the max MMR difference growth based on the number of concurrent players.
            """
            def max_diff(wait, q):
                if q < 6:
                    base, growth = 125, 75
                elif q < 12:
                    base, growth = 100, 50
                else:
                    base, growth = 75, 25
                step = 6         # number of queue attempts, not number of seconds
                return base + (wait // step) * growth # no cap, eventually guaranteeing a match
            ```
        - 6a. If any players exist within the MMR_delta in the follow side, pair this player with them
        - 6b. Otherwise, don't pair
    - 7. Repeat Step 6 until the lead side has been iterated through, then leave the remaining players in X, Y, and Z for next wave

When a match is actually found, we need to generate parameters for the match:
- Obviously, we need to get the Discord IDs and user IDs of the players
    - However, we should hide the Discord IDs on the frontend and only display user IDs
    - We should also display the nationality of each player, e.g., ":flag_kr: Classic"
- A random map will be chosen from the maps in the pool that neither has generated
- Server choice will be determined by looking at the server cross-table in /data
- In-game channel will be `scevo` appended by a random 3-digit string

We should use these parameters