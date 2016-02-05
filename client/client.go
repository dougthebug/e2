package client

import (
    "fmt"
    "net/http"
    "time"
)

type NotFound struct {
    ID      int
}

func (err NotFound) Error() string {
    return fmt.Sprintf("Not Found: %v", err.ID)
}

type Options struct {
    URL     URL             `long:"e2-jsonrpc-url" value-name:"http://IP:9999/"`
    Timeout time.Duration   `long:"e2-jsonrpc-timeout" default:"10s"`
}

func (options Options) Client() (*Client, error) {
    if options.URL.Empty() {
        return nil, fmt.Errorf("No URL given")
    }

    client := &Client{
        url:        options.URL,
        httpClient: &http.Client{
            Timeout:    options.Timeout,
        },
    }

    return client, nil
}

type Client struct {
    url             URL
    httpClient      *http.Client
    seq             int

    // internal state
    sourceCache         cacheMap
    auxCache            cacheMap
    screenCache         cacheMap
}

func (client *Client) updateSources() error {
    // list
    sources, err := client.ListSources()
    if err != nil {
        return err
    }

    // map
    updateMap := make(cacheMap)

    for _, source := range sources {
        updateMap[source.ID] = source
    }

    client.sourceCache.apply("source", updateMap)

    return nil
}

func (client *Client) getSources() (cacheMap, error) {
    if client.sourceCache == nil {
        // TODO: invalidate
        if err := client.updateSources(); err != nil {
            return nil, err
        }
    }

    return client.sourceCache, nil
}

func (client *Client) Sources() (sources []Source, err error) {
    if cacheMap, err := client.getSources(); err != nil {
        return nil, err
    } else {
        for _, value := range cacheMap {
            sources = append(sources, value.(Source))
        }

        return sources, nil
    }
}

func (client *Client) Source(id int) (Source, error) {
    if cacheMap, err := client.getSources(); err != nil {
        return Source{}, err
    } else if value, exists := cacheMap[id]; !exists {
        return Source{}, NotFound{id}
    } else {
        return value.(Source), nil
    }
}

func (client *Client) updateDestinations() error {
    // list
    listDestinations, err := client.ListDestinations()
    if err != nil {
        return err
    }

    // map
    auxMap := make(cacheMap)
    screenMap := make(cacheMap)

    for _, auxDestination := range listDestinations.AuxDestination {
        auxMap[auxDestination.ID] = auxDestination
    }
    for _, screenDestination := range listDestinations.ScreenDestination {
        screenMap[screenDestination.ID] = screenDestination
    }

    client.auxCache.apply("aux", auxMap)
    client.screenCache.apply("screen", screenMap)

    return nil
}

func (client *Client) getAuxes() (cacheMap, error) {
    if client.auxCache == nil {
        // TODO: invalidate
        if err := client.updateDestinations(); err != nil {
            return nil, err
        }
    }

    return client.auxCache, nil
}

func (client *Client) AuxDestinations() (items []AuxDestination, err error) {
    if cacheMap, err := client.getAuxes(); err != nil {
        return nil, err
    } else {
        for _, value := range cacheMap {
            items = append(items, value.(AuxDestination))
        }

        return items, nil
    }
}

func (client *Client) AuxDestination(id int) (ret AuxDestination, err error) {
    if cacheMap, err := client.getAuxes(); err != nil {
        return ret, err
    } else if value, exists := cacheMap[id]; !exists {
        return ret, NotFound{id}
    } else {
        return value.(AuxDestination), nil
    }
}

func (client *Client) getScreens() (cacheMap, error) {
    if client.screenCache == nil {
        // TODO: invalidate
        if err := client.updateDestinations(); err != nil {
            return nil, err
        }
    }

    return client.screenCache, nil
}

func (client *Client) ScreenDestinations() (items []ScreenDestination, err error) {
    if cacheMap, err := client.getScreens(); err != nil {
        return nil, err
    } else {
        for _, value := range cacheMap {
            items = append(items, value.(ScreenDestination))
        }

        return items, nil
    }
}

func (client *Client) ScreenDestination(id int) (ret ScreenDestination, err error) {
    if cacheMap, err := client.getScreens(); err != nil {
        return ret, err
    } else if value, exists := cacheMap[id]; !exists {
        return ret, NotFound{id}
    } else {
        return value.(ScreenDestination), nil
    }
}
