import pytest

from catanatron_arena.agents import load_pi_agents_config
from catanatron_arena.agents.docker_pi import DEFAULT_ENV_PASSTHROUGH, DEFAULT_IMAGE


def write(tmp_path, contents):
    path = tmp_path / "agents.toml"
    path.write_text(contents, encoding="utf-8")
    return path


def test_minimal_entry_uses_defaults(tmp_path):
    path = write(
        tmp_path,
        """
        [agents.claude]
        provider = "anthropic"
        model = "claude-opus-4-5"
        """,
    )

    configs = load_pi_agents_config(path)

    assert set(configs.keys()) == {"claude"}
    cfg = configs["claude"]
    assert cfg.provider == "anthropic"
    assert cfg.model == "claude-opus-4-5"
    assert cfg.image == DEFAULT_IMAGE
    assert cfg.move_timeout_seconds == 30.0
    assert cfg.max_invalid_retries == 2
    assert cfg.cpus == 2.0  # default in DockerPiAgentConfig
    assert cfg.memory_mb == 2048
    assert cfg.network is None
    assert cfg.env_passthrough == DEFAULT_ENV_PASSTHROUGH
    assert cfg.name == "pi:claude"


def test_overrides_apply(tmp_path):
    path = write(
        tmp_path,
        """
        [agents.opus]
        provider = "anthropic"
        model = "claude-opus-4-5"
        image = "my-arena-agent:latest"
        move_timeout_seconds = 60
        max_invalid_retries = 5
        cpus = 4.0
        memory_mb = 8192
        network = "none"
        env_passthrough = ["ANTHROPIC_API_KEY", "OPENAI_API_KEY"]
        """,
    )

    cfg = load_pi_agents_config(path)["opus"]

    assert cfg.image == "my-arena-agent:latest"
    assert cfg.move_timeout_seconds == 60.0
    assert cfg.max_invalid_retries == 5
    assert cfg.cpus == 4.0
    assert cfg.memory_mb == 8192
    assert cfg.network == "none"
    assert cfg.env_passthrough == ("ANTHROPIC_API_KEY", "OPENAI_API_KEY")


def test_multiple_entries(tmp_path):
    path = write(
        tmp_path,
        """
        [agents.claude]
        provider = "anthropic"
        model = "claude-opus-4-5"

        [agents.gpt]
        provider = "openai"
        model = "gpt-4-turbo"
        move_timeout_seconds = 45
        """,
    )

    configs = load_pi_agents_config(path)

    assert configs["claude"].provider == "anthropic"
    assert configs["gpt"].provider == "openai"
    assert configs["gpt"].move_timeout_seconds == 45.0


def test_missing_required_keys_raises(tmp_path):
    path = write(
        tmp_path,
        """
        [agents.claude]
        provider = "anthropic"
        """,
    )

    with pytest.raises(ValueError, match="missing required key"):
        load_pi_agents_config(path)


def test_unknown_keys_raise(tmp_path):
    path = write(
        tmp_path,
        """
        [agents.claude]
        provider = "anthropic"
        model = "claude-opus-4-5"
        tiimeout_seconds = 30
        """,
    )

    with pytest.raises(ValueError, match="unknown key"):
        load_pi_agents_config(path)


def test_wrong_type_raises(tmp_path):
    path = write(
        tmp_path,
        """
        [agents.claude]
        provider = "anthropic"
        model = "claude-opus-4-5"
        cpus = "two"
        """,
    )

    with pytest.raises(ValueError, match="cpus must be a number"):
        load_pi_agents_config(path)


def test_env_passthrough_must_be_list_of_strings(tmp_path):
    path = write(
        tmp_path,
        """
        [agents.claude]
        provider = "anthropic"
        model = "claude-opus-4-5"
        env_passthrough = ["OK", 42]
        """,
    )

    with pytest.raises(ValueError, match="env_passthrough"):
        load_pi_agents_config(path)


def test_empty_file_returns_empty_map(tmp_path):
    path = write(tmp_path, "")
    assert load_pi_agents_config(path) == {}


def test_agents_table_must_be_a_table(tmp_path):
    path = write(
        tmp_path,
        """
        agents = "not a table"
        """,
    )
    with pytest.raises(ValueError, match=r"\[agents\] must be a table"):
        load_pi_agents_config(path)
