import yfinance as yf
import pandas as pd
import numpy as np
from pathlib import Path

# Create portfolio returns

input_path = Path(r"\\actl-share\Actuarial\GRaCA\Development\Individual - Yamurai")
output_path = Path(r"\\actl-share\Actuarial\GRaCA\Development\Individual - Yamurai")

output_path.mkdir(parents=True, exist_ok=True)

def create_asset_class_returns():
    asset_proxies = {
        "Foreign cash": "BIL",
        "Foreign global equity": "URTH",
        "Foreign interest rate instruments": "BND",
        "Foreign other equity": "VWO",
        "Local interest rate instruments": "STXGOV.JO",
        "Local listed equity": "STX40.JO",
        "Local listed property": "STXPRO.JO",
        "Local other equity": "STX40.JO",
        "Local physical property": "STXPRO.JO"
    }

    tickers = [
        ticker
        for ticker in asset_proxies.values()
        if ticker is not None
        ]

    start_date = "2015-01-01"
    end_date = None  # download up to the latest available date

    prices = yf.download(
        tickers=tickers,
        start=start_date,
        end=end_date,
        interval="1d",
        auto_adjust=True,
        progress=False,
        group_by="column"
    )

    # Extract closing prices
    if isinstance(prices.columns, pd.MultiIndex):
        close_prices = prices["Close"].copy()
    else:
        close_prices = prices[["Close"]].copy()
        close_prices.columns = tickers

    # Remove dates where every ticker is missing
    close_prices = close_prices.dropna(how="all")

    print("Adjusted closing prices:")
    print(close_prices.head())

    print(close_prices.tail())

    # convert to monthly prices
    monthly_prices = close_prices.resample("ME").last()

    # Calculate simple monthly returns
    monthly_returns = monthly_prices.pct_change(fill_method=None)

    # Remove rows where every return is missing
    monthly_returns = monthly_returns.dropna(how="all")

    # remove outliers outside 1.5 times the IQR from lower and upper quartile
    def remove_outliers_iqr(series):
        q1 = series.quantile(0.25)
        q3 = series.quantile(0.75)

        iqr = q3 - q1

        lower = q1 - 1.5 * iqr
        upper = q3 + 1.5 * iqr

        return series[(series >= lower) & (series <= upper)]

    monthly_returns_no_outliers = monthly_returns.apply(
        remove_outliers_iqr
    )

    print("\nMonthly returns:")
    print(monthly_returns.head())

    # annualise
    months_per_year = 12

    annualised_mean = monthly_returns_no_outliers.mean() * months_per_year

    annualised_volatility = (
        monthly_returns_no_outliers.std(ddof=1)
        * np.sqrt(months_per_year)
    )

    ticker_statistics = pd.DataFrame({
        "Ticker": annualised_mean.index,
        "Annualised_Mean_Return": annualised_mean.values,
        "Annualised_Volatility": annualised_volatility.values,
        "Number_of_Months": monthly_returns_no_outliers.count().values
    })

    ticker_statistics["Annualised_Mean_Return_Pct"] = (
        ticker_statistics["Annualised_Mean_Return"] * 100
    )

    ticker_statistics["Annualised_Volatility_Pct"] = (
        ticker_statistics["Annualised_Volatility"] * 100
    )

    ticker_statistics = ticker_statistics[
        [
            "Ticker",
            "Annualised_Mean_Return",
            "Annualised_Volatility",
            "Annualised_Mean_Return_Pct",
            "Annualised_Volatility_Pct",
            "Number_of_Months"
        ]
    ]

    print("\nAnnualised statistics:")
    print(ticker_statistics.round(4))

    asset_mapping = pd.DataFrame(
    [
        {
            "Asset_Class": asset_class,
            "Ticker": ticker
        }
        for asset_class, ticker in asset_proxies.items()
        if ticker is not None
    ]
)

    asset_statistics = asset_mapping.merge(
        ticker_statistics,
        on="Ticker",
        how="left"
    )

    # Adjust the data for reasonability and to account for missing tickers
    minimum_expected_return = 0.01 # physical property was negative
    maximum_expected_return = 0.0889 # attempt to make results sensible. equity too high results at 12%
    maximum_volatility = 0.20

    # Other equity is assumed to earn 1% less than listed equity,
    # with volatility 10% higher than listed equity.
    other_equity_return_adjustment = -0.01
    other_equity_volatility_multiplier = 1.10

    # Physical property is assumed to earn 2% less than listed property,
    # with volatility equal to 50% of listed property volatility.
    physical_property_return_adjustment = -0.003
    physical_property_volatility_multiplier = 0.50

    asset_statistics["Expected_Return"] = (
        asset_statistics["Annualised_Mean_Return"]
    )

    asset_statistics["Expected_Volatility"] = (
        asset_statistics["Annualised_Volatility"]
    )

    # min expected return
    asset_statistics["Expected_Return"] = (
        asset_statistics["Expected_Return"]
        .clip(lower=minimum_expected_return)
    )

    # max expected return
    asset_statistics["Expected_Return"] = (
        asset_statistics["Expected_Return"]
        .clip(upper=maximum_expected_return)
    )

    # max vol
    asset_statistics["Expected_Volatility"] = (
        asset_statistics["Expected_Volatility"]
        .clip(upper=maximum_volatility)
    )

    local_listed_equity = asset_statistics.loc[
        asset_statistics["Asset_Class"] == "Local listed equity"
    ].iloc[0]

    foreign_global_equity = asset_statistics.loc[
        asset_statistics["Asset_Class"] == "Foreign global equity"
    ].iloc[0]


    # Local other equity based on local listed equity
    local_other_equity_mask = (
        asset_statistics["Asset_Class"] == "Local other equity"
    )

    asset_statistics.loc[
        local_other_equity_mask,
        "Expected_Return"
    ] = (
        local_listed_equity["Annualised_Mean_Return"]
        + other_equity_return_adjustment
    )

    asset_statistics.loc[
        local_other_equity_mask,
        "Expected_Volatility"
    ] = (
        local_listed_equity["Annualised_Volatility"]
        * other_equity_volatility_multiplier
    )

    # listed vs physical property
    local_listed_property = asset_statistics.loc[
        asset_statistics["Asset_Class"] == "Local listed property"
    ].iloc[0]

    physical_property_mask = (
        asset_statistics["Asset_Class"] == "Local physical property"
    )

    asset_statistics.loc[
        physical_property_mask,
        "Expected_Return"
    ] = (
        local_listed_property["Expected_Return"]
        + physical_property_return_adjustment
    )

    asset_statistics.loc[
        physical_property_mask,
        "Expected_Volatility"
    ] = (
        local_listed_property["Annualised_Volatility"]
        * physical_property_volatility_multiplier
    )


    asset_statistics = asset_statistics[
        [
            "Asset_Class",
            "Ticker",
            "Annualised_Mean_Return",
            "Annualised_Volatility",
            "Expected_Return",
            "Expected_Volatility"
        ]
    ]

    asset_statistics["Expected_Volatility"] = asset_statistics["Expected_Volatility"] + 0.02 # wasn't getting negative years

    local_cash = pd.DataFrame([{"Asset_Class": "Local Cash", "Expected_Return": 0.05, "Expected_Volatility": 0.005}])

    asset_statistics = pd.concat([asset_statistics, local_cash], ignore_index = True)

    print("\nAdjusted asset-class statistics:")
    print(asset_statistics.round(4))

    # Creating projections for 100 years

    projection_years = 100
    number_of_simulations = 10_000
    initial_value = 1.0
    lower_percentile = 5
    upper_percentile = 95
    random_seed = 42

    rng = np.random.default_rng(random_seed)

    projection_results = []

    #  projections for each asset class
    for _, row in asset_statistics.iterrows():

        asset_class = str(row["Asset_Class"]).strip().lower().replace(" ", "_")
        mean_return = row["Expected_Return"]
        volatility = row["Expected_Volatility"]

        # Variance used by the normal distribution
        variance = volatility ** 2

        # Generate annual returns:
        # rows = simulations
        # columns = projection years
        simulated_returns = rng.normal(
            loc=mean_return,
            scale=np.sqrt(variance),
            size=(number_of_simulations, projection_years)
        )

        # Prevent returns below -100%, since these would create
        # negative cumulative asset values
        simulated_returns = np.maximum(simulated_returns, -1.0)

        # Calculate the cumulative value for every simulated path
        simulated_values = initial_value * np.cumprod(
            1 + simulated_returns,
            axis=1
        )

        # Calculate expected, lower and upper projected values
        
        expected_values = np.mean(simulated_values, axis=0)

        lower_values = np.percentile(
            simulated_values,
            lower_percentile,
            axis=0
        )

        upper_values = np.percentile(
            simulated_values,
            upper_percentile,
            axis=0
        )

        horizons = np.arange(1, len(expected_values) + 1)

        # Calculate annual effective rates
        expected_returns = expected_values**(1/horizons) - 1

        lower_returns = lower_values**(1/horizons) - 1

        upper_returns = upper_values**(1/horizons) - 1
        

        for year in range(1, projection_years + 1):

            projection_results.append({
                "Asset_Class": asset_class,
                "horizon_years": year,
                "expected_return_pct": expected_returns[year - 1],
                "lower_return_pct": lower_returns[year - 1],
                "upper_return_pct": upper_returns[year - 1]
            })

    # df
    projections_df = pd.DataFrame(projection_results)
    projections_df["Asset_Class"] = projections_df["Asset_Class"].str.lower().str.replace(" ", "_")

    print("\n100-year asset-class projections:")

    print(projections_df.round(4))

    projections_df.to_csv(output_path / "asset_class_returns.csv",
        index=False
    )


def create_portfolio_returns() -> list[dict]:
    """Calculate portfolio-level return curves from:

    - asset_class_returns.csv
    - portfolio_weightings.csv
    - portfolios.csv

    For each portfolio and horizon:

        portfolio return =
            sum(asset-class weight * asset-class return)

    Returns a list of portfolio-return dictionaries.
    """

    asset_return_rows = pd.read_csv(
        input_path / "asset_class_returns.csv"
    ).to_dict(orient="records")

    portfolio_weight_rows = pd.read_csv(
        input_path / "portfolio_weightings.csv"
    ).to_dict(orient="records")


    # Structure:
    #
    # asset_returns[horizon][asset_class] = {
    #     "expected": value,
    #     "lower": value,
    #     "upper": value
    # }

    asset_returns: dict[
        float,
        dict[str, dict[str, float]]
    ] = {}

    for row_number, row in enumerate(
        asset_return_rows,
        start=2
    ):

        asset_class = str(row["Asset_Class"]).strip().lower().replace(" ", "_")

        horizon = float(
            row["horizon_years"]
        )

        expected = float(
            row["expected_return_pct"]
        )

        lower = float(
            row["lower_return_pct"]
        )

        upper = float(
            row["upper_return_pct"]
        )

        if horizon < 0:
            raise ValueError(
                f"horizon_years cannot be negative: "
                f"{horizon}"
            )

        if lower > expected:
            raise ValueError(
                f"lower_return_pct ({lower}) is greater "
                f"than expected_return_pct ({expected})"
            )

        if expected > upper:
            raise ValueError(
                f"expected_return_pct ({expected}) is "
                f"greater than upper_return_pct ({upper})"
            )

        asset_returns.setdefault(
            horizon,
            {}
        )

        if asset_class in asset_returns[horizon]:
            raise ValueError(
                f"Duplicate return assumption for asset "
                f"class '{asset_class}' at horizon "
                f"{horizon}"
            )

        asset_returns[horizon][asset_class] = {
            "expected": expected,
            "lower": lower,
            "upper": upper,
        }

    return_asset_classes = {
        asset_class
        for returns_at_horizon in asset_returns.values()
        for asset_class in returns_at_horizon
    }

    # Identify columns in portfolio_weightings.csv
    weighting_headers = list(
        portfolio_weight_rows[0].keys()
    )

    
    print(weighting_headers)

    fund_code_column = next(
        (
            column
            for column in weighting_headers
            if str(column).strip().lower().replace(" ", "_") == "fund_code"
        ),
        None,
    )

    if fund_code_column is None:
        raise ValueError(
            "portfolio_weightings.csv must contain "
            "a 'FUND CODE' column"
        )

    # Match normalised asset-class names to CSV headings
    weighting_asset_columns = {
        str(column).strip().lower().replace(" ", "_"): column
        for column in weighting_headers
        if column != fund_code_column
    }

    missing_weight_columns = sorted(
        return_asset_classes
        - set(weighting_asset_columns)
    )

    if missing_weight_columns:
        raise ValueError(
            "The following asset classes occur in "
            "asset_class_returns.csv but do not have "
            "corresponding columns in "
            "portfolio_weightings.csv: "
            + ", ".join(missing_weight_columns)
        )

    portfolio_returns: list[dict] = []

    for row_number, row in enumerate(
        portfolio_weight_rows,
        start=2
    ):
        original_portfolio_key = str(
            row[fund_code_column]
        ).strip()

        portfolio_key = original_portfolio_key

        if not portfolio_key:
            raise ValueError(
                "Portfolio fund code is blank"
            )

        weights: dict[str, float] = {}

        for asset_class in return_asset_classes:
            csv_column = weighting_asset_columns[
                asset_class
            ]

            raw_weight = row.get(csv_column)

            if (
                raw_weight is None
                or str(raw_weight).strip() == ""
            ):
                weight = 0.0
            else:
                weight = float(raw_weight)

            weights[asset_class] = weight

        total_weight = sum(weights.values())

        if abs(total_weight - 1.0) > 0.001:
            raise ValueError(
                f"Portfolio "
                f"'{original_portfolio_key}' weights "
                f"sum to {total_weight:.8f}, not 1.0"
            )

        for horizon in sorted(asset_returns):
            returns_at_horizon = asset_returns[
                horizon
            ]

            # Identify non-zero weights for which there is no
            # corresponding return assumption.
            missing_assumptions = sorted(
                asset_class
                for asset_class, weight in weights.items()
                if abs(weight) > 1e-12
                and asset_class not in returns_at_horizon
            )

            if missing_assumptions:
                raise ValueError(
                    f"Portfolio "
                    f"'{original_portfolio_key}' has "
                    f"non-zero weights for asset classes "
                    f"without return assumptions at "
                    f"horizon {horizon}: "
                    + ", ".join(missing_assumptions)
                )

            expected_return = sum(
                weight
                * returns_at_horizon[
                    asset_class
                ]["expected"]
                for asset_class, weight in weights.items()
                if asset_class in returns_at_horizon
            )

            lower_return = sum(
                weight
                * returns_at_horizon[
                    asset_class
                ]["lower"]
                for asset_class, weight in weights.items()
                if asset_class in returns_at_horizon
            )

            upper_return = sum(
                weight
                * returns_at_horizon[
                    asset_class
                ]["upper"]
                for asset_class, weight in weights.items()
                if asset_class in returns_at_horizon
            )

            portfolio_returns.append({
                "portfolio_key": original_portfolio_key,
                "horizon_years": horizon,
                "expected_return_pct": expected_return,
                "lower_return_pct": lower_return,
                "upper_return_pct": upper_return,
            })

    portfolio_returns_df = pd.DataFrame(portfolio_returns)
    portfolio_returns_df.to_csv(
        output_path / "portfolio_returns.csv",
        index=False
    )
    print(f"\nPortfolio returns saved to: {output_path / 'portfolio_returns.csv'}")
    return portfolio_returns

create_asset_class_returns()
create_portfolio_returns()