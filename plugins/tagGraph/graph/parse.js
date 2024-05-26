function parse(source) {
    const nodes = []
    const edges = []
    for (const tag of source.data.findTags.tags) {
      nodes.push({
          id: tag.id,
          shape: "circularImage", // could also just use "image" here
          image: tag.image_path,
          label: tag.name
      })
      for (const child of tag.children) {
          edges.push({from:tag.id, to:child.id})
      }
    }
    return { nodes, edges }
}

async function getTags() {

  const query = `query FindTags($filter: FindFilterType, $tag_filter: TagFilterType) {
      findTags(filter: $filter, tag_filter: $tag_filter) {
              count
              tags {
                  id
                  name
                  image_path
                  parents { id }
                  children { id }
              }
      }
  }`
  const variables = {
      "tag_filter": {
          "child_count": {"modifier": "GREATER_THAN", "value": 0},
          "OR": {"parent_count": {"modifier": "GREATER_THAN", "value": 0}},
      },
      "filter": {"q": "", "per_page": -1},
  }
  const source = await fetch("/graphql", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query:query, variables:variables })
  }).then(r => r.json())
  console.log(`Found ${source.data.findTags.count} tags with parents/children`)
  return parse(source)

}
var network = null;

async function draw() {

  var container = document.getElementById("taggraph");
  var data = await getTags();

  console.log(data)

  var options = {
    autoResize: true,
    height: `${window.screen.height}px`, //100% does not seem to work here
    width: "100%",
    configure: { enabled: false }, //set to true to enable config options
    nodes: {
      color: {
        border: "#adb5bd",
        background: "#394b59",
        highlight: {
          border: "#137cbd",
          background: "#FFFFFF"
        }
      },
      font: { color: "white" },
    },
    edges: {
      color: "#FFFFFF"
    },
    layout: {
      improvedLayout: false
    }
  };
  network = new vis.Network(container, data, options);
}